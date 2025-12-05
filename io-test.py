#!/bin/env python
import subprocess
from subprocess import Popen, PIPE, CalledProcessError
import textwrap
import os

with open("/tmp/echo", "w") as fp:
    fp.write(
        textwrap.dedent(
            """
            #!/bin/bash
            for ((i=0;$i<10;i++)); do
                date
                sleep 1
            done
            """.lstrip()
        )
    )
os.system("chmod +x /tmp/echo")

with Popen(["/tmp/echo"], stderr=subprocess.STDOUT, stdout=PIPE, bufsize=1, universal_newlines=True) as proc:
    while True:
        if proc.poll() is not None:
            print(f"child process exits: {proc.returncode}")
            break
        print("reading")
        line = proc.stdout.readline()
        print(line)
