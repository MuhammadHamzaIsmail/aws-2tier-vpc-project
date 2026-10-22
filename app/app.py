import os
import uuid
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key
from flask import Flask, redirect, render_template_string, request
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB uploads

REGION = os.environ.get("AWS_REGION", "us-east-1")
BUCKET = os.environ["S3_BUCKET"]
TABLE = os.environ.get("DDB_TABLE", "guestbook-messages")

s3 = boto3.client("s3", region_name=REGION)
table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)

PAGE = """<!doctype html>
<title>Cloud Guestbook</title>
<h1>Cloud Guestbook</h1>
<p>Served by EC2 &middot; data in DynamoDB &middot; images in S3</p>
<form method="post" enctype="multipart/form-data">
  <input name="name" placeholder="Your name" required>
  <input name="message" placeholder="Message" required>
  <input type="file" name="image" accept="image/*">
  <button>Post</button>
</form>
<hr>
{% for m in messages %}
  <p><b>{{ m.name }}</b>: {{ m.message }} <small>{{ m.time }} UTC</small>
  {% if m.url %}<br><img src="{{ m.url }}" width="200">{% endif %}</p>
{% endfor %}
"""


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        now = datetime.now(timezone.utc).isoformat()
        item = {
            "pk": "guestbook",
            "created_at": f"{now}#{uuid.uuid4().hex[:8]}",
            "name": request.form["name"],
            "message": request.form["message"],
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
        r["time"] = r["created_at"][:19].replace("T", " ")
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
    return render_template_string(PAGE, messages=rows)


@app.route("/health")
def health():
    return "ok"