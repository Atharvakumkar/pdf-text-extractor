import boto3
import fitz
import os
import urllib.parse

s3 = boto3.client("s3")

def lambda_handler(event, context):

    input_bucket = event["Records"][0]["s3"]["bucket"]["name"]
    file_key = urllib.parse.unquote_plus(
        event["Records"][0]["s3"]["object"]["key"]
    )

    if not file_key.endswith(".pdf"):
        print(f"Skipping non-PDF file: {file_key}")
        return {"statusCode": 200, "body": "Not a PDF, skipped."}

    print(f"Processing: {file_key} from bucket: {input_bucket}")

    response = s3.get_object(Bucket=input_bucket, Key=file_key)
    pdf_bytes = response["Body"].read()

    pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
    full_text = ""

    for page_num in range(len(pdf_document)):
        page = pdf_document[page_num]
        full_text += page.get_text() + "\n"

    pdf_document.close()

    print(f"Extraction successful. Characters extracted: {len(full_text)}")

    output_bucket = os.environ["OUTPUT_BUCKET"]
    output_key = file_key.replace("uploads/", "extracted/").replace(".pdf", ".txt")

    s3.put_object(
        Bucket=output_bucket,
        Key=output_key,
        Body=full_text,
        ContentType="text/plain"
    )

    print(f"Text saved to: s3://{output_bucket}/{output_key}")

    return {
        "statusCode": 200,
        "body": f"Text extracted and saved to {output_key}"
    }
