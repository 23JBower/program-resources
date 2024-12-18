import socket
from multiprocessing import Process
import ast
import os
import time
import threading
import cryptocode
import sendgrid
from sendgrid.helpers.mail import Mail
import random
import requests

BASE = os.getcwd()
HOST = "localhost"  # Bind to localhost
PORT = 65432        # Port to listen on

global SENDGRID
SENDGRID = cryptocode.decrypt("hqub4lR6wQRrixYQIrG2nrt76xbvz39gYdnHTE3Nqfd14Ewr9WGCgPc78u9GGcXKDOUKQmG7jmxeou7qDVCFURDTMRXt*Mi6cZUp5a891BEL2O5eVpQ==*Iq8s5v5Qbj4VaTzhOTGNXg==*0fEUhie7vI5/5KPEGG+PRA==", input('Key: '))

clients_heartbeats = {}

def debug(data):
    DEBUG = True
    if DEBUG:
        print(data)

class SimpleSnowflake:
    def __init__(self):
        self.sequence = 0
        self.last_timestamp = -1
        self.lock = threading.Lock()

    def _current_millis(self):
        return int(time.time() * 1000)

    def generate_id(self):
        with self.lock:
            timestamp = self._current_millis() % 1000000  # Get the last 6 digits of the timestamp

            if timestamp == self.last_timestamp:
                self.sequence = (self.sequence + 1) % 1000  # 3 digits for sequence
                if self.sequence == 0:
                    while timestamp <= self.last_timestamp:
                        timestamp = self._current_millis() % 1000000
            else:
                self.sequence = 0

            self.last_timestamp = timestamp

            # Combine timestamp and sequence to create a 12-digit ID
            snowflake_id = f"{timestamp:06d}{self.sequence:03d}"
            return snowflake_id

def send_client(csock, data):
    attempts = 0
    while True:
        debug('sending')
        try:
            csock.settimeout(10)
            csock.send(bytes(f'{data}', 'utf-8'))
            debug(('OUT:', data))
            break
        except socket.timeout:
            attempts += 1
            if attempts == 3:
                print(f"Client timed out")
                csock.close()
                break

def send_email(receiver_email, subject, message):
    global SENDGRID
    sg = sendgrid.SendGridAPIClient(api_key=SENDGRID)
    email = Mail(
        from_email='pythonmessagingservice@gmail.com',
        to_emails=receiver_email,
        subject=subject,
        plain_text_content=message
    )
    try:
        response = sg.send(email)
        print(f"Email sent successfully! Status code: {response.status_code}")
    except Exception as e:
        print(f"An error occurred: {e}")

def heartbeat_client(csock, addr):
    while True:
        if addr not in clients_heartbeats or (clients_heartbeats[addr] - time.time() > 30):
            print(f"Client at address: {addr} timed out")
            csock.close()
            break

def recv_client(csock, addr):
    attempts = 0
    debug('awaiting')
    while True:
        try:
            csock.settimeout(10)
            data = csock.recv(1024).decode('utf-8')
            if data != '':
                try:
                    data = ast.literal_eval(data)
                    debug(('IN:', data))
                except Exception as e:
                    print("RECEIVED FORMAT ERROR:", data)
                if data[0] == '00':
                    clients_heartbeats[addr] = time.time()
                    send_client(csock, ['01'])
                else:
                    return data
            else:
                attempts += 1
                if attempts == 3:
                    print(f"Client at address: {addr} timed out")
                    csock.close()
                    break
        except socket.timeout:
            attempts += 1
            if attempts == 3:
                print(f"Client at address: {addr} timed out")
                csock.close()
                break

def info_user(username):
    os.chdir(BASE + '/data')
    with open('accounts', 'r') as f:
        accounts = ast.literal_eval(f.read())
    for account in accounts:
        if account[1] == username.lower():
            os.chdir(BASE)
            return account
    os.chdir(BASE)
    return None
            
def create_user(username, password, email, csock, addr):
    debug(3)
    if info_user(username) is not None:
        return ['120']
    else:
        debug(4)
        os.chdir(BASE + '/data')
        with open('accounts', 'r') as f:
            accounts = ast.literal_eval(f.read())
        code = random.randint(100000, 999999)
        debug(5)
        send_email(email, "Verify Email", f"""Thanks for signing up to PMS!
        Your verification code is: {code}
        
        If this was not you you can ignore this email""")
        debug(6)
        send_client(csock, ['122'])
        debug(7)
        verify = int(recv_client(csock, addr)[1])
        debug(8)
        if code == verify:
            uid = snowflake.generate_id()
            accounts.append([uid, username.lower(), cryptocode.encrypt(password, password), email.lower()])
            with open('accounts', 'w') as f:
                f.write(f'{accounts}')
                os.chdir(BASE)
                return ['121', [uid, username.lower()]]
        else:
            return ['123']

def login_user(username, password):
    user = info_user(username)
    if user == None:
        return ['110']
    else:
        os.chdir(BASE + '/data')
        hashed = user[2]
        if cryptocode.decrypt(hashed, password) == password:
            return ['112', [user[0], user[1]]]
        else:
            return ['111']

def handle_client(csock, addr):
    while True:
        debug(1)
        request = recv_client(csock, addr)
        try:
            if request[0] == '10':
                data = info_user(request[1])
                if data is not None:
                    send_client(csock, ['100', [data[0], data[1]]])
                else:
                    send_client(csock, ['101'])

            elif request[0] == '11':
                data = login_user(request[1], request[2])
                if data[0] == '110':
                    send_client(csock, ['110'])
                elif data[0] == '111':
                    send_client(csock, ['111'])
                elif data[0] == '112':
                    user = [data[1][0], data[1][1]]
                    send_client(csock, ['112'])

            elif request[0] == '12':
                debug(2)
                data = create_user(request[1], request[2], request[3], csock, addr)
                if data[0] == '120':
                    send_client(csock, ['120'])
                else:
                    send_client(csock, [data[0]])
                    clients_heartbeats[addr] = time.time()
        except TypeError as e:
            print(e)
            return

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen()
    print(f"Server listening on {HOST}:{PORT}", requests.get('https://api.ipify.org').text)

    while True:
        client_socket, addr = server.accept()
        print(f"Accepted connection from {addr}")
        newclient = Process(target=handle_client, args=(client_socket, addr))
        newclient.start()
        time.sleep(5)
        clients_heartbeats[addr] = time.time()
        newheartbeat = Process(target=heartbeat_client, args=(client_socket, addr))
        newheartbeat.start()

if __name__ == "__main__":
    snowflake = SimpleSnowflake()
    start_server()
