import asyncio
import logging
import os

from singleton import Singleton


class AsyncSSHHandler(metaclass=Singleton):
    """
    A class for handling SSH connections and tunnels.
    """

    SSH_HOST = os.getenv("SSH_HOST")
    SSH_PORT = int(os.getenv("SSH_PORT"))
    SSH_USER = os.getenv("SSH_USER")
    SSH_PASSWORD = os.getenv("SSH_PASSWORD")
    FORWARDS = [
        # {
        #     "listen_host": "localhost",
        #     "listen_port": 6379,
        #     "dest_host": "localhost",
        #     "dest_port": 6379,
        # }
    ]

    async def initialize(self):
        await self.start_ssh_tunnel()

    async def start_ssh_tunnel(self):
        import asyncssh

        try:
            await asyncio.sleep(2)
            tunnel = await asyncssh.connect(
                host=self.SSH_HOST,
                port=self.SSH_PORT,
                username=self.SSH_USER,
                password=self.SSH_PASSWORD,
                known_hosts=None,
            )
            for forward in self.FORWARDS:
                if all(
                    key in forward
                    for key in ["listen_host", "listen_port", "dest_host", "dest_port"]
                ):
                    listener = await tunnel.forward_local_port(**forward)
            logging.info("SSH tunnel established successfully.")
            return listener
        except Exception as e:
            logging.error(f"Failed to establish SSH tunnel: {e}")
            raise
