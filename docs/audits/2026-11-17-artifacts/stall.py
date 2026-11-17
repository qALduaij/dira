# A local RTSP endpoint that accepts the connection and then never answers: models a hung upstream.
import socket, subprocess, time, threading
srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(); port = srv.getsockname()[1]
conns = []
threading.Thread(target=lambda: conns.append(srv.accept()), daemon=True).start()
cmd = ["ffmpeg","-nostdin","-loglevel","error","-threads","1","-rtsp_transport","tcp","-i",f"rtsp://127.0.0.1:{port}/x",
       "-map","0:a:0","-vn","-ac","1","-ar","16000","-f","s16le","pipe:1"]   # exact production audio arguments
p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
time.sleep(45)
print("ffmpeg alive after 45s with zero output bytes:", p.poll() is None)
p.kill(); p.wait(); srv.close()
