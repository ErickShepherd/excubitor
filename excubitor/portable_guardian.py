"""Internal POSIX lifeline guardian. Trusted cooperative programs only.

The parent retains a pipe to this process. Parent loss kills this session's
process group. A live parent kills the group before reaping its leader, so no
saved PID or check-then-signal identity race is involved. A guardian crash AND
owner loss has no recovery proof; the watchdog deliberately refuses that case.
"""

import base64
import json
import os
import select
import signal
import subprocess
import sys
import threading

LINEAGE = "_EXCUBITOR_POSIX_LINEAGE_FD"


def main():
    status = int(sys.argv[1])
    lineage = int(os.environ[LINEAGE])
    # Unbuffered read is essential: buffered readline can hide lifeline bytes.
    request = bytearray()
    while not request.endswith(b"\n"):
        chunk = os.read(0, 65536)
        if not chunk or len(request) > 2 * 1024 * 1024:
            return 70
        request.extend(chunk)
    value = json.loads(request)
    process = subprocess.Popen(value["argv"], stdin=subprocess.PIPE, close_fds=True, pass_fds=(lineage,))
    os.write(status, (json.dumps({"pid": process.pid}) + "\n").encode())

    def feed():
        try:
            process.stdin.write(base64.b64decode(value["stdin"], validate=True))
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    threading.Thread(target=feed, daemon=True).start()
    # Only the actual program/descendants now hold captured output handles.
    os.close(1)
    os.close(2)
    reported = False
    while True:
        if select.select([0], [], [], 0.01)[0] and not os.read(0, 1):
            os.killpg(os.getpgrp(), signal.SIGKILL)
        code = process.poll()
        if code is not None and not reported:
            os.write(status, (json.dumps({"exit_code": code}) + "\n").encode())
            reported = True
        # Stay alive as the unreaped group identity anchor until our owner kills
        # the group. Even after the program exits its descendants belong here.


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BaseException:
        # An initialization failure must not strand already-launched children.
        os.killpg(os.getpgrp(), signal.SIGKILL)
