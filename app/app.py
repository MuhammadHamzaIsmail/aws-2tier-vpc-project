import os
import uuid
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key
from flask import Flask, redirect, render_template, request
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB uploads

REGION = os.environ.get("AWS_REGION", "us-east-1")
BUCKET = os.environ["S3_BUCKET"]
TABLE = os.environ.get("DDB_TABLE", "guestbook-messages")

s3 = boto3.client("s3", region_name=REGION)
table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:50]
        message = request.form.get("message", "").strip()[:500]
        if not name or not message:
            return redirect("/")

        now = datetime.now(timezone.utc).isoformat()
        item = {
            "pk": "guestbook",
            "created_at": f"{now}#{uuid.uuid4().hex[:8]}",
            "name": name,
            "message": message,
        }
        f = request.files.get("image")
        if f and f.filename:
            key = f"uploads/{uuid.uuid4()}-{secure_filename(f.filename)}"
            s3.upload_fileobj(f, BUCKET, key, ExtraArgs={"ContentType": f.content_type})
            item["image_key"] = key
        table.put_item(Item=item)
        return redirect("/")

    resp = table.query(
        KeyConditionExpression=Key("pk").eq("guestbook"),
        ScanIndexForward=False,  # newest first
        Limit=50,
    )
    rows = resp["Items"]
    for r in rows:
        r["iso"] = r["created_at"].split("#")[0]
        r["time"] = r["created_at"][:16].replace("T", " ")
        r["initial"] = r["name"][:1].upper()
        r["hue"] = sum(map(ord, r["name"])) % 360
        key = r.get("image_key")
        r["url"] = (
            s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": BUCKET, "Key": key},
                ExpiresIn=3600,
            )
            if key
            else None
        )
    return render_template("index.html", messages=rows)


@app.errorhandler(413)
def too_large(_):
    return "Photo is too large. Please go back and choose one under 5 MB.", 413


@app.route("/health")
def health():
    return "ok"