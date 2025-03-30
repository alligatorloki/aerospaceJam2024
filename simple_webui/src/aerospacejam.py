import network
import socket
import json

def capitalize_first_letter(s: str) -> str:
    """
    Capitalizes the first letter of the passed string and returns it.
    """
    if not s:
        return s  # Return the empty string if input is empty
    return s[0].upper() + s[1:].lower()

def parse_http_request(request_bytes):
    """
    Parses raw HTTP request bytes into an HTTPRequest object.
    """
    request_text = request_bytes.decode('utf-8', 'ignore')
    lines = request_text.split("\n")
    req = HTTPRequest()
    if lines:
        # Parse the request line, e.g.: GET /index.html HTTP/1.1
        request_line = lines[0].strip()
        parts = request_line.split()
        if len(parts) >= 3:
            req.method = parts[0]
            req.path = parts[1]
            req.version = parts[2]
        # Parse headers until an empty line is found
        index = 1
        while index < len(lines):
            line = lines[index].strip()
            index += 1
            if line == "":
                break
            if ":" in line:
                header_name, header_value = line.split(":", 1)
                req.headers[header_name.strip()] = header_value.strip()
        # The remainder (if any) is the body
        req.body = "\n".join(lines[index:]).strip()
    return req


class HTTPRequest:
    """
    Class for holding HTTP request data.
    """
    def __init__(self, method="", path="", version="", headers={}, body=""):
        self.method = method
        self.path = path
        self.version = version
        self.headers = headers
        self.body = body


class HTTPResponse:
    """
    Class for holding HTTP response data.
    """
    def __init__(self, status=200, reason="OK", headers={
        "Content-Type": "text/html",
        "Connection": "close"
    }, body=""):
        self.status = status
        self.reason = reason
        self.headers = headers
        self.body = body

def response_html(body):
    """
    Returns an HTTPResponse object with a body of type text/html.
    """
    return HTTPResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "text/html"
        },
        body=body
    )

def response_json(body):
    """
    Returns an HTTPResponse object with a body of type application/json.
    """
    return HTTPResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "application/json"
        },
        body=json.dumps(body)
    )

class AerospaceJamServer:
    """
    A barebones realtime WebUI implementation for the Aerospace Jam.
    """
    def __init__(self, config: dict, register_default_paths=True):
        """
        Initializes the server and starts the Wi-Fi AP.
        
        Args:
        - config: a dictionary containing AP settings.
        - register_default_paths: whether to register the default paths (/ and /sensors) or not.
        """
        self.config = config
        self.sensors = {}
        self.paths = {}
        self.ap = None
        self.template = self.load_template('webui.html')
        
        if register_default_paths:
            self.register_path('/sensors', self.sensors_handler)
            self.register_path('/', self.index_handler)

        self.start_wifi_ap()

    def start_wifi_ap(self):
        """
        Starts a Wi-Fi AP with the config stored in obj.config.
        """
        self.ap = network.WLAN(network.AP_IF)
        self.ap.config(essid=self.config['ssid'], password=self.config['password'])
        self.ap.ifconfig((self.config['static_ip'], self.config['subnet_mask'], self.config['gateway'], self.config['dns']))
        self.ap.active(True)
        print(f"Hotspot {self.config['ssid']} started with IP: {self.config['static_ip']}")

    def register_sensor(self, name, read_function):
        """
        Registers a sensor to the WebUI.
        
        Args:
        - name: The name of the sensor, displayed in the WebUI.
        - read_function: The function that is called when the sensor is read from - should return an object that can be converted to a string.
        """
        self.sensors[name] = read_function

    def register_path(self, path, handler):
        """
        Registers a custom path to the server.
        
        Args:
        - handler: A function that takes a single parameter - the HTTPRequest object. It should return an HTTPResponse object.
        """
        self.paths[path] = handler

    def sensors_handler(self, req):
        """
        Handles the /sensors path.
        """
        sensor_data = {name: read_func() for name, read_func in self.sensors.items()}
        return response_json(sensor_data)
    
    def index_handler(self, req):
        """
        Handles the / path.
        """
        sensor_data = {name: read_func() for name, read_func in self.sensors.items()}
        web_page = self.generate_web_page(sensor_data)
        return response_html(web_page)

    def load_template(self, template_path):
        """
        Loads a template from a given filesystem path.
        """
        with open(template_path, 'r') as file:
            return file.read()

    def generate_web_page(self, sensor_values):
        """
        Generates the WebUI from a template.
        """
        sensor_data_html = ""
        update_js = ""

        for name, value in sensor_values.items():
            sensor_name = capitalize_first_letter(name)
            sensor_data_html += f'<p>{sensor_name}: <span id="{name}">{value}</span></p>\n'
            update_js += f'document.getElementById("{name}").innerText = data["{name}"];\n'

        return self.template.replace("{{sensor_data_html}}", sensor_data_html).replace("{{ip}}", self.config['static_ip']).replace("{{update_js}}", update_js)

    def send_response(self, conn, response: HTTPResponse):
        """
        Sends an HTTPResponse object to the client.
        """
        response_line = f"HTTP/1.1 {response.status} {response.reason}\r\n"
        
        if "Content-Length" not in response.headers:
            response.headers["Content-Length"] = str(len(response.body.encode('utf-8')))
        
        headers = ""
        for header, value in response.headers.items():
            headers += f"{header}: {value}\r\n"
        
        http_response = response_line + headers + "\r\n" + response.body
        conn.sendall(http_response.encode('utf-8'))

    def handle_client(self, conn):
        """
        Handles an open connection from a client - a single web request.
        """
        request_bytes = conn.recv(1024)
        req = parse_http_request(request_bytes)

        if req.path in self.paths:
            response = self.paths[req.path](req)
        else:
            response = HTTPResponse(
                status=404,
                reason="Not Found",
                body="Path not found! Have you registered it with server.register_path()?"
            )
        
        self.send_response(conn, response)
        conn.close()

    def run(self):
        """
        Runs the server, blocks until an error or an interrupt.
        """
        addr = socket.getaddrinfo(self.config['static_ip'], 80)[0][-1]
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # Reuse the address
        s.bind(addr)
        s.listen(1)
        
        print(f'Web server running on http://{self.config["static_ip"]}/')

        try:
            while True:
                conn, addr = s.accept()
                print('Got a request from %s' % str(addr))
                self.handle_client(conn)
        finally:
            s.close()



