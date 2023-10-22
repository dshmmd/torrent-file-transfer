import asyncio
import datetime
import os
import random
import socket
from collections import defaultdict
import sys
import colorama
from colorama import Fore as ChangeColor


class Tracker(asyncio.Protocol):
    def __init__(self):
        self.files = defaultdict(set)
        self.file_logs = defaultdict(list)
        self.all_logs = list()
        self.keep_alive_logs = list()

    def connection_made(self, transport):
        self.transport = transport

    def connection_lost(self, exc):
        self.transport.close()

    def datagram_received(self, data, addr):
        message = data.decode().split()
        mode, filename, listen_addr = message[0], message[1], eval(message[2])
        file_path = f"{listen_addr[1]}/{filename}"

        print(f"{listen_addr} wants to {mode} {filename}")
        self.all_logs.append(f"{listen_addr} wants to {mode} {filename}")
        self.file_logs[filename].append(f"{datetime.datetime.now()}::{listen_addr} wants to {mode} {file_path}")

        if mode == "share":
            if os.path.exists(file_path):
                self.files[filename].add(listen_addr)
                self.transport.sendto(b"SUCCESS", addr)

                print(f"{listen_addr} is sharing {filename}")
                self.all_logs.append(f"{listen_addr} is sharing {filename}")
                self.file_logs[filename].append(f"{datetime.datetime.now()}::{listen_addr} is sharing {filename}")
            else:
                self.transport.sendto(b"ERROR", addr)

                print(f"{listen_addr} can not share {filename} because it does not exists")
                self.all_logs.append(f"{listen_addr} can not share {filename} because it does not exists")
                self.file_logs[filename].append(f"{datetime.datetime.now()}::{listen_addr} can not share {filename} because it does not exists")

        elif mode == "get":
            if filename in self.files and self.files[filename]:
                print(f"{listen_addr} can get {filename} from these addresses: {self.files[filename]}")
                self.all_logs.append(f"{listen_addr} can get {filename} from these addresses: {self.files[filename]}")
                self.file_logs[filename].append(
                    f"{datetime.datetime.now()}::{listen_addr} can get {filename} from these addresses: {self.files[filename]}")

                sharing_peers = tuple(self.files[filename])
                selected_peer = str(random.choice(sharing_peers))
                self.transport.sendto(selected_peer.encode(), addr)

                print(f"{listen_addr} is getting {filename} from {selected_peer}")
                self.all_logs.append(f"{listen_addr} is getting {filename} from {selected_peer}")
                self.file_logs[filename].append(f"{datetime.datetime.now()}::{listen_addr} is getting {filename} from {selected_peer}")

            else:
                self.transport.sendto(b"ERROR", addr)

                print(f"{listen_addr} failed to get {filename} because it was not registered in tracker")
                self.all_logs.append(f"{listen_addr} failed to get {filename} because it was not registered in tracker")
                self.file_logs[filename].append(
                    f"{datetime.datetime.now()}::{listen_addr} failed to get {filename} because it was not registered in tracker")


async def keep_alive(tracker):
    keep_alive_logs = tracker.keep_alive_logs
    while True:
        files = tracker.files
        for file, peers in files.items():
            dead_peers = set()
            for peer in peers:
                sock = socket.socket()
                try:
                    sock.connect(peer)
                    sock.send(b"PING")
                    log = f"{datetime.datetime.now()}::Keep-alive PING sent to {peer}: "
                    response = sock.recv(150).decode()
                    log += f"{response} received"

                except Exception:
                    dead_peers.add(peer)
                    log = f"{datetime.datetime.now()}::Keep-alive protocol removed {peer} from tracker"
                    print(f"Keep-alive protocol removed {peer} from tracker")

                keep_alive_logs.append(log)
                sock.close()
            peers -= dead_peers
        await asyncio.sleep(3)


async def process_input(tracker):
    while True:
        print("file_logs <filename/all>, keep_alive_logs, all_logs")
        try:
            user_input = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
            user_input = user_input.strip()
        except KeyboardInterrupt:
            print("No more logs")
            print(ChangeColor.RESET)
            break
        except asyncio.CancelledError:
            return
        except Exception:
            return

        all_logs = tracker.all_logs
        file_logs = tracker.file_logs
        keep_alive_logs = tracker.keep_alive_logs

        print(ChangeColor.CYAN)
        if user_input.startswith("file_logs"):
            file = user_input.split()[1]
            if file == "all" and file_logs:
                for file, all_logs in file_logs.items():
                    print(f"Logs of {file}:")
                    for log in all_logs:
                        print(log)
            elif file_logs[file]:
                for log in file_logs[file]:
                    print(log)
            else:
                print("No log yet")

        elif user_input == "keep_alive_logs":
            if keep_alive_logs:
                for log in keep_alive_logs: print(log)
            else:
                print("No log yet")

        elif user_input == "all_logs":
            if all_logs:
                for log in all_logs: print(log)
            else:
                print("No log yet")
        elif user_input == "exit":
            print('no more logs')
            print(ChangeColor.RESET)
            break
        else:
            print("Wrong input")

        print(ChangeColor.RESET)


async def main():
    colorama.init()
    try:
        ip, port = sys.argv[1].split(':')
        port = int(port)
    except IndexError:
        ip, port = "127.0.0.1", 65000

    tracker = Tracker()
    loop = asyncio.get_running_loop()

    try:
        transport, protocol = await loop.create_datagram_endpoint(lambda: tracker, local_addr=(ip, port))
    except KeyboardInterrupt:
        print("Tracker process terminated")
        return
    except Exception as e:
        print(f"Error creating datagram endpoint: {e}")
        return

    keep_alive_task = asyncio.create_task(keep_alive(tracker))
    input_task = asyncio.create_task(process_input(tracker))
    print(f"Tracker listening on {ip}:{port}")

    try:
        await asyncio.gather(keep_alive_task, input_task, asyncio.sleep(3600))
    except KeyboardInterrupt:
        print("Tracker process terminated")
        keep_alive_task.cancel()
        input_task.cancel()
        try:
            await keep_alive_task
        except asyncio.CancelledError:
            pass
        try:
            await input_task
        except asyncio.CancelledError:
            pass
    except RuntimeError as e:
        print(f"RuntimeError: {e}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        transport.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Tracker process terminated")
