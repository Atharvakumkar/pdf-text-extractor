# Event Driven Serverless PDF Text Extraction Pipeline

A serverless PDF text extraction pipeline built on AWS. The system automatically processes PDF files the moment they are uploaded to S3, extracts text page by page using PyMuPDF, and writes the output as a plain text file to a separate S3 bucket. The entire pipeline is event-driven with no persistent compute infrastructure.

## Table of Contents

- [Architecture](#architecture)
- [Execution Flow](#execution-flow)
- [Project Structure](#project-structure)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Deployment](#deployment)
- [Configuration](#configuration)
- [Lambda Function](#lambda-function)
- [Lambda Layer](#lambda-layer)
- [Implementation Notes](#implementation-notes)
- [Observability](#observability)
- [Author](#author)
- [License](#license)

---

## Architecture

The pipeline is composed of the following AWS services:

- **Amazon S3 (Input Bucket)** — receives uploaded PDF files under the `uploads/` prefix
- **Amazon S3 (Output Bucket)** — stores extracted text files under the `extracted/` prefix
- **AWS Lambda** — executes the extraction logic on demand, triggered by S3 events
- **S3 Event Notifications** — fires on `s3:ObjectCreated:Put` events filtered by prefix (`uploads/`) and suffix (`.pdf`)
- **Lambda Layers** — packages PyMuPDF and its native dependencies in a Linux-compatible format separately from the function code
- **IAM Roles** — grants Lambda the minimum required permissions to read from the input bucket and write to the output bucket
- **Amazon CloudWatch** — captures Lambda logs, execution metrics, and error events

Separate input and output buckets are used intentionally to prevent the output write from re-triggering the Lambda function.

---

## Execution Flow

```
Upload PDF to input bucket (uploads/<filename>.pdf)
        |
        v
S3 Event Notification fires (PUT, prefix: uploads/, suffix: .pdf)
        |
        v
Lambda function invoked
        |
        v
PDF read directly into memory from S3
        |
        v
Text extracted page by page using PyMuPDF (fitz)
        |
        v
Output written to output bucket (extracted/<filename>.txt)
        |
        v
Lambda execution terminates
```

---

## Project Structure

```
pdf-text-extractor/
|
|-- lambda_function.py        # Core Lambda handler; reads PDF, extracts text, writes output
|-- function.zip              # Deployable package of lambda_function.py
|-- pymupdf-layer.zip         # Lambda Layer containing PyMuPDF built for Linux (Amazon Linux 2)
|
|-- layer-build/              # Scripts and instructions used to build the Lambda Layer
|-- layer-final/python/       # Final compiled Python packages included in the layer
|-- layer-packages/           # Intermediate build artifacts for layer compilation
```

---

## Tech Stack

**Runtime**

- Python 3.x (AWS Lambda)

**AWS Services**

- AWS Lambda
- Amazon S3
- S3 Event Notifications
- AWS IAM
- Amazon CloudWatch
- Lambda Layers

**Libraries**

- [PyMuPDF (fitz)](https://pymupdf.readthedocs.io/) — PDF parsing and text extraction
- boto3 — AWS SDK for Python; used to interact with S3
- urllib.parse — URL-decodes S3 object keys to handle special characters in filenames

---

## Prerequisites

- An AWS account with permissions to create Lambda functions, S3 buckets, IAM roles, and CloudWatch log groups
- AWS CLI configured locally (`aws configure`)
- Python 3.x

---

## Deployment

### 1. Create S3 Buckets

Create two separate S3 buckets: one for input and one for output.

```bash
aws s3 mb s3://your-input-bucket-name
aws s3 mb s3://your-output-bucket-name
```

### 2. Create the IAM Role

Create an execution role for Lambda with the following permissions:

- `s3:GetObject` on the input bucket
- `s3:PutObject` on the output bucket
- `logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents` for CloudWatch

Attach the `AWSLambdaBasicExecutionRole` managed policy as a baseline, then add an inline policy for S3 access.

### 3. Deploy the Lambda Layer

Upload the pre-built layer containing PyMuPDF:

```bash
aws lambda publish-layer-version \
  --layer-name pymupdf-layer \
  --zip-file fileb://pymupdf-layer.zip \
  --compatible-runtimes python3.11
```

Note the `LayerVersionArn` returned in the output.

### 4. Deploy the Lambda Function

```bash
aws lambda create-function \
  --function-name pdf-text-extractor \
  --runtime python3.11 \
  --role arn:aws:iam::<account-id>:role/<your-role-name> \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://function.zip \
  --layers <LayerVersionArn> \
  --environment Variables={OUTPUT_BUCKET=your-output-bucket-name} \
  --timeout 60 \
  --memory-size 256
```

### 5. Configure S3 Event Notification

Grant S3 permission to invoke the Lambda function:

```bash
aws lambda add-permission \
  --function-name pdf-text-extractor \
  --statement-id s3-trigger \
  --action lambda:InvokeFunction \
  --principal s3.amazonaws.com \
  --source-arn arn:aws:s3:::your-input-bucket-name
```

Then add the event notification to the input bucket via the AWS Console or a bucket notification configuration JSON targeting the `s3:ObjectCreated:Put` event with prefix filter `uploads/` and suffix filter `.pdf`.

---

## Configuration

The Lambda function reads the output bucket name from an environment variable. This must be set at deployment time or updated via the console or CLI.

| Variable | Description |
|---|---|
| `OUTPUT_BUCKET` | Name of the S3 bucket where extracted text files are written |

---

## Lambda Function

`lambda_function.py` is the sole application file. Its behavior on each invocation:

1. Parses the S3 bucket name and object key from the event payload.
2. URL-decodes the object key to handle filenames with spaces or special characters.
3. Skips execution if the file does not have a `.pdf` extension.
4. Reads the PDF file directly into memory using `s3.get_object()`.
5. Opens the in-memory bytes as a PDF document using `fitz.open()`.
6. Iterates over each page, calling `page.get_text()` and concatenating the result.
7. Derives the output key by replacing the `uploads/` path prefix with `extracted/` and the `.pdf` extension with `.txt`.
8. Writes the extracted text to the output bucket using `s3.put_object()` with `ContentType: text/plain`.
9. Returns a 200 status code with the output key in the response body.

---

## Lambda Layer

PyMuPDF includes C and C++ native extensions that must be compiled for the Lambda execution environment (Amazon Linux 2). The pre-built layer `pymupdf-layer.zip` is provided in this repository and is ready to publish directly.

If you need to rebuild the layer for a different runtime version, use the `layer-build/` directory which contains the build scripts. The general process is to install PyMuPDF inside a Docker container running the Amazon Linux 2 image, then zip the resulting `python/` directory.

---

## Implementation Notes

- **Separate input and output buckets** prevent the `.txt` output from re-triggering the Lambda function, which would occur if both operations targeted the same bucket.
- **Prefix and suffix filters** on the S3 event notification ensure the trigger fires only for PDF files under the `uploads/` path, avoiding noise from other object types or prefixes.
- **The output bucket name is stored in an environment variable** rather than hardcoded in the function, keeping the function portable across environments.
- **PyMuPDF is packaged as a Lambda Layer** rather than bundled in the function zip. This separates dependency management from function code and keeps the deployment package small.
- **The PDF is read entirely into memory** rather than written to `/tmp`. For very large PDFs, increasing the Lambda memory allocation will improve performance and reduce the risk of timeout.

---

## Observability

All Lambda invocations are logged to Amazon CloudWatch Logs under the log group `/aws/lambda/pdf-text-extractor`. Each execution logs:

- The input bucket and file key being processed
- The number of characters extracted
- The output path the text was written to
- Any errors or skipped files

CloudWatch Metrics captures invocation count, duration, error rate, and throttle count automatically.

---

## Author

Atharva Kumkar

---

## License

This project is licensed under the MIT License.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files, to deal in the software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the software, and to permit persons to whom the software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
