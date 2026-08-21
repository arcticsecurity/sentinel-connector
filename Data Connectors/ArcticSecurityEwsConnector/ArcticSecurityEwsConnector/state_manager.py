import logging

from azure.storage.fileshare import ShareClient, ShareFileClient
from azure.core.exceptions import ResourceNotFoundError

logger = logging.getLogger(__name__)


class StateManager:
    def __init__(
        self,
        connection_string,
        share_name="funcstatemarkershare",
        file_path="funcstatemarkerfile",
    ):
        self.share_cli = ShareClient.from_connection_string(
            conn_str=connection_string, share_name=share_name
        )
        self.file_cli = ShareFileClient.from_connection_string(
            conn_str=connection_string, share_name=share_name, file_path=file_path
        )

    def post(self, token: str):
        try:
            self.file_cli.upload_file(token)
        except ResourceNotFoundError:
            logger.info("Must create share")
            self.share_cli.create_share()
            self.file_cli.upload_file(token)

    def get(self):
        try:
            return self.file_cli.download_file().readall().decode()
        except ResourceNotFoundError:
            return None
