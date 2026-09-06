"""Start a generated-content recording for manual/native bar Pause and Stop checks."""
import argparse,json,os,time
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import QApplication,QLabel
from omnishot.theme import ThemeManager
from omnishot import backend
from omnishot.app import Controller
from omnishot.widgets import place_window

parser=argparse.ArgumentParser();parser.add_argument("output",type=Path);parser.add_argument("--isolated-workspace",action="store_true");args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
os.environ["OMNISHOT_DATA_DIR"]=str(out/"data")
app=QApplication([]);app.setApplicationName("omnishot");app.setDesktopFileName("org.omarchy.OmniShot");theme=ThemeManager(app)
server=QLocalServer();server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
if not server.listen(f"omnishot-{os.getuid()}"):raise RuntimeError("Close the running OmniShot app before this test")
original_workspace=backend.hypr("activeworkspace")["id"];test_workspace=None
if args.isolated_workspace:
    used={w["id"] for w in backend.hypr("workspaces")};test_workspace=next(i for i in range(1,100) if i not in used)
    backend.run(["hyprctl","eval",f'hl.dispatch(hl.dsp.focus({{workspace="{test_workspace}"}}))'])
controller=Controller(app);clients=[];commands=[]
def connection():
    sock=server.nextPendingConnection();clients.append(sock);buffer=bytearray()
    def read():
        buffer.extend(bytes(sock.readAll()))
        if b"\n" in buffer:
            args=json.loads(buffer.split(b"\n")[0]);commands.append(args["command"]);controller.dispatch(args);sock.disconnectFromServer()
    sock.readyRead.connect(read)
server.newConnection.connect(connection)
window=QLabel("OmniShot bar control verification\n\nRight-click the recording timer to pause/resume.\nClick it to finish.");window.setWindowTitle("OmniShot Bar Test");window.resize(660,400);window.show();place_window(window,100,100)
def completed(path):
    report={"recording":str(path),"commands":commands,"pause_resume_stop":commands.count("pause")>=2 and "stop" in commands};(out/"report.json").write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True);QTimer.singleShot(200,app.quit)
controller.edit=completed
def start():
    client=next(c for c in backend.hypr("clients") if c["title"]==window.windowTitle())
    opts={"mode":"Area","format":"MP4","fps":15,"quality":"high","size":"Native","system":False,"mic":False,"cursor":False,"delay":0}
    controller.launch_recorder((*client["at"],*client["size"]),opts)
    print("READY: recording generated content; bar controls can now be exercised",flush=True)
QTimer.singleShot(800,start);QTimer.singleShot(90000,app.quit)
try:app.exec()
finally:
    server.close();window.close()
    if test_workspace and backend.hypr("activeworkspace")["id"]==test_workspace:backend.run(["hyprctl","eval",f'hl.dispatch(hl.dsp.focus({{workspace="{original_workspace}"}}))'])
