import tarfile
from pathlib import Path
from typing import TYPE_CHECKING

import boto3

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


def download_index(bucket: str, key: str, destination: Path) -> None:
    """Download and extract an operator-created Chroma archive from S3."""
    archive_path = destination / "index.tar.gz"
    index_path = destination / "chroma_db"

    s3: S3Client = boto3.client("s3")
    s3.download_file(bucket, key, str(archive_path))

    with tarfile.open(archive_path, mode="r:gz") as archive:
        members = archive.getmembers()

        # Our index archive needs only regular files and directories.
        if any(not (member.isfile() or member.isdir()) for member in members):
            raise RuntimeError("Index archive contains unsupported file types.")

        archive.extractall(index_path, members=members, filter="data")

    if not (index_path / "chroma.sqlite3").is_file():
        raise RuntimeError("Index archive is missing chroma.sqlite3.")

    archive_path.unlink()