import asyncio
import socket
import argparse
import os


async def handle_client(reader, writer):
    message = await reader.read(150)
    message = message.decode(errors="ignore")

    if message.startswith("GET"):
        file_name = message.split()[1]
        peer_addr = eval(message.split()[2])
        sock_port = writer.get_extra_info("sockname")[1]
        file_path = f"{sock_port}/{file_name}"
        print(f"New request for {file_path} from {peer_addr}")

        if os.path.exists(file_path):
            print(f"Sending {file_path} to {peer_addr}")

            with open(file_path, 'rb') as file:
                chunk_size = 256
                while True:
                    chunk = file.read(chunk_size)
                    if not chunk: break
                    writer.write(chunk)
                    await writer.drain()
                writer.write(b"\x00SUCCESS")

            print(f"{file_name} sent to {peer_addr} successfully")
        else:
            writer.write(b"\x00ERROR")
            print(f"Can not find {file_path}")
        writer.close()
        await writer.wait_closed()

    elif message == "PING":
        writer.write(b"PONG")
        await writer.drain()
        writer.close()
        await writer.wait_closed()
    else:
        print(f"Can not recognize message <<{message}>> from {writer.get_extra_info('peername')}")
        writer.close()
        await writer.wait_closed()


async def start_sharing(filename, listen_addr):
    print(f"Trying to share {filename} on {listen_addr}")
    server = await asyncio.start_server(handle_client, *listen_addr)
    print(f"Sharing on {listen_addr}")
    async with server:
        await server.serve_forever()


async def start_getting(filename, my_addr, source_addr):
    print(f"Trying to get {filename} from {source_addr}")
    source_addr = eval(source_addr)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(source_addr)
        sock.send(f"GET {filename} {str(my_addr).replace(' ', '')}".encode())
    except ConnectionError:
        print(f"Can not connect to {source_addr}")

    print(f"Getting from {source_addr}")
    with open(f"{my_addr[1]}/{filename}", "wb") as f:
        while True:
            try:
                sock.settimeout(5)
                chunk = sock.recv(256)
            except socket.timeout:
                print(f"{filename} was not received from {source_addr} completely")
                return "ERROR"

            if chunk == b"ERROR":
                print(f"{filename} was not received from {source_addr}")
                return "ERROR"
            elif chunk.endswith(b"\x00SUCCESS"):
                f.write(chunk.split(b"\x00")[0])
                print(f"{filename} received from {source_addr} successfully")
                return "SUCCESS"
            else:
                f.write(chunk)


async def send_request(mode, filename, listen_addr, tracker_addr):
    message = f"{mode} {filename} {str(listen_addr).replace(' ', '')}"
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(message.encode(), tracker_addr)
    sock.settimeout(5)

    try:
        data, addr = sock.recvfrom(1500)
    except ConnectionResetError:
        raise Exception("Can not connect to tracker")

    return data.decode()


async def share(filename, listen_addr, tracker_addr):
    print(f"Trying to register {filename} on tracker:", end=' ')
    try:
        response = await send_request("share", filename, listen_addr, tracker_addr)
    except Exception as e:
        print(e)
        exit(1)
    print(response)

    if response == "SUCCESS":
        await start_sharing(filename, listen_addr)
    else:
        print(f"Can not register {filename} on tracker")
        exit(1)


async def get(filename, listen_addr, tracker_addr):
    print(f"Trying to find {filename} in tracker:", end=' ')
    try:
        response = await send_request("get", filename, listen_addr, tracker_addr)
    except Exception as e:
        print(e)
        exit(1)
    print(response if response == "ERROR" else "SUCCESS")

    if response != "ERROR":
        return await start_getting(filename, listen_addr, response)
    else:
        print(f"Can not find {filename} in tracker")
        exit(1)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['share', 'get'])
    parser.add_argument('filename')
    parser.add_argument('listen')
    parser.add_argument('--tracker', default=f'127.0.0.1:65000')
    args = parser.parse_args()

    mode = args.mode
    filename = args.filename

    tracker_addr = args.tracker.split(":")
    tracker_addr = (tracker_addr[0], int(tracker_addr[1]))

    listen_addr = args.listen.split(":")
    peer_port = listen_addr[1]
    listen_addr = (listen_addr[0], int(listen_addr[1]))

    if not os.path.exists(peer_port):
        os.mkdir(peer_port)

    print(f"Listening will be on: {listen_addr[0]}:{listen_addr[1]}")

    if mode == "share":
        if os.path.exists(f"{peer_port}/{filename}"):
            await share(filename, listen_addr, tracker_addr)
        else:
            print(f"Can not share {filename} because it does not exist in your directory {peer_port}")
    elif mode == "get":
        get_status = await get(filename, listen_addr, tracker_addr)
        if get_status == "SUCCESS": await share(filename, listen_addr, tracker_addr)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Peer process terminated")
