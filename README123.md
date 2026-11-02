<<<<<<< HEAD
# CloudDocs - Flask + Amazon S3 document portal

## Features
- Client registration and login
- Password hashing
- Per-user file ownership checks
- Upload files directly to S3 (no permanent EC2 upload copy)
- List, search, filter, preview, download and delete
- MySQL stores user accounts and file metadata

## 1. Create the MySQL database
Run this in your RDS MySQL database using an administrator account:

```sql
CREATE DATABASE document_portal CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Create a dedicated database user and grant it access to this database. Avoid using the RDS master account for the application.

## 2. Configure environment variables
Set these variables in your local terminal or EC2 service environment:

- `FLASK_SECRET_KEY`: long random secret
- `DB_HOST`: RDS endpoint (hostname only)
- `DB_PORT`: usually 3306
- `DB_NAME`: document_portal
- `DB_USER`: application database username
- `DB_PASSWORD`: application database password
- `S3_BUCKET_NAME`: exact existing bucket name
- `AWS_DEFAULT_REGION`: region containing the bucket

Do not commit `.env`, credentials, or secret values to GitHub.

## 3. Local setup (Windows PowerShell)
```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:FLASK_SECRET_KEY="replace-with-a-long-random-secret"
$env:DB_HOST="your-rds-endpoint"
$env:DB_PORT="3306"
$env:DB_NAME="document_portal"
$env:DB_USER="your-app-user"
$env:DB_PASSWORD="your-app-password"
$env:S3_BUCKET_NAME="your-bucket-name"
$env:AWS_DEFAULT_REGION="us-east-1"
```

For local development, configure AWS credentials using an approved local AWS profile (`aws configure` or AWS IAM Identity Center). Never place access keys in source code. EC2 should use its attached IAM role.

Initialize the tables:
```powershell
flask --app app init-db
```

Run locally:
```powershell
flask --app app run --debug
```
Open http://127.0.0.1:5000

## 4. GitHub
```bash
git init
git add .
git commit -m "Initial CloudDocs application"
git branch -M main
git remote add origin YOUR_GITHUB_REPOSITORY_URL
git push -u origin main
```

## 5. EC2 deployment outline
Clone the repository on EC2, create a Python virtual environment, install requirements, set the environment variables securely, and run:
```bash
flask --app app init-db
gunicorn --workers 2 --bind 127.0.0.1:8000 app:app
```
For production, run Gunicorn under systemd and put Nginx in front with HTTPS. Do not expose Flask's development server directly to the internet.

## Notes
- The IAM role attached to EC2 needs `s3:ListBucket`, `s3:GetBucketLocation`, `s3:PutObject`, `s3:GetObject`, and `s3:DeleteObject` scoped to your bucket and its objects.
- The RDS security group must allow TCP 3306 from the EC2 security group.
- Bucket Block Public Access should remain enabled.
- Upload limit is 16 MB; adjust `MAX_CONTENT_LENGTH` if needed.
- For production, use HTTPS, secure cookies, a strong secret, backups, monitoring, and consider malware scanning and stricter content validation.
=======
# S3-RDS-EC2-Flask_app-host-_via-gunicorn
>>>>>>> 9bdc645695397f109a327cb62252ce80db80061d
