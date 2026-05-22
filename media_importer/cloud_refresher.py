import os
import subprocess
import json
import logging
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

DEFAULT_RC_SOCKET = "/var/run/rclone/rcd_1000.sock"


class CloudRefresher:
    def __init__(self, rc_socket: str = DEFAULT_RC_SOCKET):
        self.rc_socket = rc_socket
        self.available = self._check_available()

    def _check_available(self) -> bool:
        if not os.path.exists(self.rc_socket):
            logger.warning(f"Rclone RC socket not found: {self.rc_socket}")
            return False
        return True

    def _call_rc(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        if not self.available:
            return {"error": "Rclone RC not available"}

        cmd = ["curl", "--unix-socket", self.rc_socket, "-s", "-X", "POST", f"http://localhost/{endpoint}"]
        if params:
            for k, v in params.items():
                cmd.extend(["-d", f"{k}={v}"])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                logger.error(f"Rclone RC call failed: {result.stderr}")
                return {"error": result.stderr}
            return json.loads(result.stdout)
        except Exception as e:
            logger.error(f"Rclone RC call exception: {e}")
            return {"error": str(e)}

    def list_vfses(self) -> List[str]:
        result = self._call_rc("vfs/list")
        if "error" in result:
            return []
        return result.get("vfses", [])

    def refresh(self, fs: Optional[str] = None, path: str = "/") -> Dict:
        params = {"path": path}
        if fs:
            params["fs"] = fs
        return self._call_rc("vfs/refresh", params)

    def refresh_all(self) -> Dict:
        vfses = self.list_vfses()
        results = {}
        for vfs in vfses:
            results[vfs] = self.refresh(fs=vfs, path="/")
        return results
