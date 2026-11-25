import config


class LocalStorage:
    kind = "local"

    def __init__(self, root):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, key, data, content_type):
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def read(self, key):
        return (self.root / key).read_bytes()

    def download_url(self, key, filename):
        return None


class S3Storage:
    kind = "s3"

    def __init__(self, bucket):
        import boto3
        self.bucket = bucket
        self.s3 = boto3.client("s3", region_name=config.AWS_REGION)

    def save(self, key, data, content_type):
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type,
                           ServerSideEncryption="AES256")

    def read(self, key):
        return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def download_url(self, key, filename):
        return self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key,
                    "ResponseContentDisposition": f'inline; filename="{filename}"'},
            ExpiresIn=300,
        )


def create_storage():
    if config.is_aws():
        return S3Storage(config.S3_BUCKET)
    return LocalStorage(config.DATA_DIR / "uploads")
