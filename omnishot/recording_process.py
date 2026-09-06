"""Bounded process shutdown for takes the user explicitly chose to discard."""
import signal
import subprocess
import os
from pathlib import Path


def launch_encoder(command, *, env=None, lease_fd=None, **kwargs):
    """Bind an encoder's lifetime to this app, including when it is paused."""
    guard=Path(__file__).resolve().parent.parent/"native/recording-guard.so"
    if not guard.is_file():
        raise RuntimeError("OmniShot's recording components need rebuilding. Run install.sh from the OmniShot folder.")
    env=dict(os.environ if env is None else env)
    owner=os.pidfd_open(os.getpid())
    library=None
    try:
        library=os.open(guard,os.O_RDONLY|os.O_CLOEXEC)
        env["OMNISHOT_RECORD_OWNER_FD"]=str(owner)
        # LD_PRELOAD splits on spaces/colons; /proc also supports install paths
        # containing either without silently losing the lifetime guard.
        env["OMNISHOT_RECORD_LIBRARY_FD"]=str(library)
        env["LD_PRELOAD"]=f"/proc/self/fd/{library}"+(":"+env["LD_PRELOAD"] if env.get("LD_PRELOAD") else "")
        descriptors=[owner,library]
        env.pop("OMNISHOT_RECORD_LEASE_FD",None)
        if lease_fd is not None:
            descriptors.append(lease_fd);env["OMNISHOT_RECORD_LEASE_FD"]=str(lease_fd)
        return subprocess.Popen(command,env=env,pass_fds=descriptors,**kwargs)
    finally:
        os.close(owner)
        if library is not None:os.close(library)


def stop_discarded_process(process,grace=3,terminate_timeout=2):
    if process is None:return
    for request,timeout in ((lambda:process.send_signal(signal.SIGINT),grace),(process.terminate,terminate_timeout),(process.kill,2)):
        if process.poll() is not None:return
        try:request()
        except ProcessLookupError:pass
        try:process.wait(timeout=timeout);return
        except subprocess.TimeoutExpired:continue
    raise RuntimeError('The cancelled recorder did not exit. Try cancelling again.')
