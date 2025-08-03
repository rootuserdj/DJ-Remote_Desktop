import sys
import socket
import threading
import zlib
import numpy as np
import cv2
import pyautogui
import time # For frame rate limiting

from PySide6.QtWidgets import (QApplication, QWidget, QPushButton, QLabel, QVBoxLayout,
                               QHBoxLayout, QLineEdit, QFrame, QStatusBar,
                               QGraphicsDropShadowEffect)
from PySide6.QtCore import (QTimer, Qt, QPropertyAnimation, QEasingCurve, QRect, QPoint,
                            QObject, Signal, QEvent)
from PySide6.QtGui import QImage, QPixmap, QFont, QLinearGradient, QPainter, QBrush, QColor, QKeyEvent

# Custom Signal for updating UI from non-GUI threads
class StatusSignal(QObject):
    message = Signal(str, str) # message, type (info, success, error)

class DJRemoteDesktop(QWidget):
    # Instantiate custom signal
    status_signal = StatusSignal()

    def __init__(self):
        super().__init__()
        # Updated: Shorter and more concise window title
        self.setWindowTitle("DJ Remote Desktop")
        self.setGeometry(150, 50, 1280, 720)
        self.setStyleSheet("background-color: #1A202C;")

        # Connect custom signal to update_status slot
        self.status_signal.message.connect(self.update_status)

        # Networking variables
        self.client_socket = None
        self.server_socket = None # To explicitly store server socket
        self.server_connection = None # To store client connection on server
        self.server_address = None # To store client address on server
        self.local_ip = self._get_local_ip() # Get local IP on startup

        # Flags to control threads and application state
        self.is_server_running = False
        self.is_client_connected = False
        self.is_streaming = False # Indicates if a screen stream is actively running (server or client receiving)

        # Thread references
        self.input_handler_thread = None
        self.screen_stream_thread = None # For server's screen capture and sending
        self.client_receive_thread = None # For client's screen receiving

        # Main layout: Sidebar + Content
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        sidebar = QFrame()
        sidebar.setFixedWidth(300)
        sidebar.setObjectName("sidebar")
        sidebar.setStyleSheet("""
            #sidebar {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2C528B, stop:1 #2A4365); /* Darker, sophisticated blue gradient */
                border-radius: 0 20px 20px 0; /* More pronounced border-radius */
            }
        """)
        # Apply QGraphicsDropShadowEffect to sidebar
        shadow_effect_sidebar = QGraphicsDropShadowEffect(sidebar)
        shadow_effect_sidebar.setBlurRadius(15)
        shadow_effect_sidebar.setXOffset(5)
        shadow_effect_sidebar.setYOffset(0) # Shadow to the right
        shadow_effect_sidebar.setColor(QColor(0, 0, 0, 100)) # Semi-transparent black
        sidebar.setGraphicsEffect(shadow_effect_sidebar)


        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(25, 25, 25, 25)
        sidebar_layout.setSpacing(20)

        # Sidebar Title
        title = QLabel("DJ Remote")
        # Updated: Slightly larger font for the sidebar title
        title.setFont(QFont("Inter", 25, QFont.Bold))
        title.setStyleSheet("color: #E2E8F0; margin-bottom: 25px;")
        title.setAlignment(Qt.AlignCenter)

        # IP Input
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("Server IP (e.g., 192.168.x.x)")
        self.ip_input.setStyleSheet("""
            QLineEdit {
                padding: 15px;
                border: 2px solid #4A5568;
                border-radius: 10px;
                background-color: #2D3748;
                color: #E2E8F0;
                font-size: 16px;
                selection-background-color: #4FD1C5;
            }
            QLineEdit:focus {
                border-color: #63B3ED;
            }
        """)
        shadow_effect_input = QGraphicsDropShadowEffect(self.ip_input)
        shadow_effect_input.setBlurRadius(10)
        shadow_effect_input.setXOffset(3)
        shadow_effect_input.setYOffset(3)
        shadow_effect_input.setColor(QColor(0, 0, 0, 80))
        self.ip_input.setGraphicsEffect(shadow_effect_input)

        # New: Label to display server IP when server is active
        self.server_ip_display_label = QLabel(f"Server IP: {self.local_ip or 'N/A'}")
        self.server_ip_display_label.setStyleSheet("""
            QLabel {
                padding: 15px;
                border: 2px solid #4A5568;
                border-radius: 10px;
                background-color: #2D3748;
                color: #E2E8F0;
                font-size: 16px;
                font-weight: bold;
                text-align: center;
            }
        """)
        self.server_ip_display_label.setAlignment(Qt.AlignCenter)
        self.server_ip_display_label.setVisible(False) # Initially hidden

        # Buttons
        self.start_server_button = QPushButton("🚀 Start Server")
        self.start_server_button.clicked.connect(self.start_server)
        self.start_server_button.setObjectName("startButton")
        self.start_server_button.setStyleSheet("""
            #startButton {
                background-color: #38A169;
                color: white;
                padding: 15px;
                border-radius: 10px;
                font-size: 18px;
                font-weight: bold;
                border: none;
            }
            #startButton:hover {
                background-color: #2F855A;
            }
            #startButton:pressed {
                background-color: #276749;
            }
            #startButton:disabled {
                background-color: #4A5568;
                color: #A0AEC0;
            }
        """)
        shadow_effect_server = QGraphicsDropShadowEffect(self.start_server_button)
        shadow_effect_server.setBlurRadius(10)
        shadow_effect_server.setXOffset(3)
        shadow_effect_server.setYOffset(3)
        shadow_effect_server.setColor(QColor(0, 0, 0, 80))
        self.start_server_button.setGraphicsEffect(shadow_effect_server)

        self.stop_server_button = QPushButton("🛑 Stop Server")
        self.stop_server_button.clicked.connect(self.stop_server)
        self.stop_server_button.setObjectName("stopServerButton")
        self.stop_server_button.setStyleSheet("""
            #stopServerButton {
                background-color: #E53E3E;
                color: white;
                padding: 15px;
                border-radius: 10px;
                font-size: 18px;
                font-weight: bold;
                border: none;
            }
            #stopServerButton:hover {
                background-color: #C53030;
            }
            #stopServerButton:pressed {
                background-color: #9B2C2C;
            }
            #stopServerButton:disabled {
                background-color: #4A5568;
                color: #A0AEC0;
            }
        """)
        shadow_effect_stop_server = QGraphicsDropShadowEffect(self.stop_server_button)
        shadow_effect_stop_server.setBlurRadius(10)
        shadow_effect_stop_server.setXOffset(3)
        shadow_effect_stop_server.setYOffset(3)
        shadow_effect_stop_server.setColor(QColor(0, 0, 0, 80))
        self.stop_server_button.setGraphicsEffect(shadow_effect_stop_server)


        self.start_client_button = QPushButton("🔌 Connect Client") # Changed text
        self.start_client_button.clicked.connect(self.start_client)
        self.start_client_button.setObjectName("clientButton")
        self.start_client_button.setStyleSheet("""
            #clientButton {
                background-color: #D69E2E;
                color: white;
                padding: 15px;
                border-radius: 10px;
                font-size: 18px;
                font-weight: bold;
                border: none;
            }
            #clientButton:hover {
                background-color: #B7791F;
            }
            #clientButton:pressed {
                background-color: #975A16;
            }
            #clientButton:disabled {
                background-color: #4A5568;
                color: #A0AEC0;
            }
        """)
        shadow_effect_client = QGraphicsDropShadowEffect(self.start_client_button)
        shadow_effect_client.setBlurRadius(10)
        shadow_effect_client.setXOffset(3)
        shadow_effect_client.setYOffset(3)
        shadow_effect_client.setColor(QColor(0, 0, 0, 80))
        self.start_client_button.setGraphicsEffect(shadow_effect_client)

        self.stop_client_button = QPushButton("❌ Disconnect Client") # Changed text
        self.stop_client_button.clicked.connect(self.stop_client_session)
        self.stop_client_button.setObjectName("stopClientButton")
        self.stop_client_button.setStyleSheet("""
            #stopClientButton {
                background-color: #E53E3E;
                color: white;
                padding: 15px;
                border-radius: 10px;
                font-size: 18px;
                font-weight: bold;
                border: none;
            }
            #stopClientButton:hover {
                background-color: #C53030;
            }
            #stopClientButton:pressed {
                background-color: #9B2C2C;
            }
            #stopClientButton:disabled {
                background-color: #4A5568;
                color: #A0AEC0;
            }
        """)
        shadow_effect_stop_client = QGraphicsDropShadowEffect(self.stop_client_button)
        shadow_effect_stop_client.setBlurRadius(10)
        shadow_effect_stop_client.setXOffset(3)
        shadow_effect_stop_client.setYOffset(3)
        shadow_effect_stop_client.setColor(QColor(0, 0, 0, 80))
        self.stop_client_button.setGraphicsEffect(shadow_effect_stop_client)


        footer = QLabel("Made with ❤️ by Dhananjay Sah\nContact: 9824204425")
        footer.setStyleSheet("color: #A0AEC0; font-size: 13px; margin-top: 25px;")
        footer.setAlignment(Qt.AlignCenter)

        sidebar_layout.addWidget(title)
        sidebar_layout.addWidget(self.ip_input)
        sidebar_layout.addWidget(self.server_ip_display_label) # Add the new label to the layout
        # Updated: Button order as requested
        sidebar_layout.addWidget(self.start_client_button)
        sidebar_layout.addWidget(self.stop_client_button)
        sidebar_layout.addWidget(self.start_server_button)
        sidebar_layout.addWidget(self.stop_server_button)
        sidebar_layout.addStretch()
        sidebar_layout.addWidget(footer)

        # Content Area
        content_frame = QFrame()
        content_frame.setStyleSheet("""
            QFrame {
                background-color: #2D3748;
                border-radius: 20px;
                margin: 20px;
            }
        """)
        # Apply QGraphicsDropShadowEffect to content frame
        shadow_effect_content = QGraphicsDropShadowEffect(content_frame)
        shadow_effect_content.setBlurRadius(20)
        shadow_effect_content.setXOffset(0)
        shadow_effect_content.setYOffset(0)
        shadow_effect_content.setColor(QColor(0, 0, 0, 120))
        content_frame.setGraphicsEffect(shadow_effect_content)


        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(30, 30, 30, 30)

        self.image_label = QLabel("Select a mode (Server/Client) to start. ✨")
        self.image_label.setStyleSheet("""
            QLabel {
                background-color: #1A202C;
                border: 2px dashed #4A5568;
                border-radius: 15px;
                color: #A0AEC0;
                font-size: 20px;
                font-weight: 500;
            }
        """)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumHeight(600)
        self.image_label.setScaledContents(False) # Important for manual scaling in update_frame
        
        # Enable mouse tracking on the image label for sending events
        self.image_label.setMouseTracking(True)
        self.image_label.installEventFilter(self) # Install event filter to capture mouse events

        # Status Bar
        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet("""
            QStatusBar {
                background-color: #2D3748;
                color: #E2E8F0;
                font-size: 15px;
                padding: 10px;
                border-top: 1px solid #4A5568;
                border-radius: 0 0 15px 15px;
            }
        """)
        self.status_bar.showMessage("Ready to connect...")

        content_layout.addWidget(self.image_label, 1)
        content_layout.addWidget(self.status_bar)

        main_layout.addWidget(sidebar)
        main_layout.addWidget(content_frame, 1)
        self.setLayout(main_layout)

        # Timer for client updates - now directly connected to a thread for receiving
        # The QTimer is no longer directly fetching frames, but triggering UI updates
        self.client_ui_update_timer = QTimer(self)
        self.client_ui_update_timer.timeout.connect(self._update_image_label_from_buffer)
        
        # Variables for image buffer
        self.latest_frame_data = None
        self.latest_frame_lock = threading.Lock() # To protect latest_frame_data

        # Enhanced status bar animation
        self.status_fade_animation = QPropertyAnimation(self.status_bar, b"windowOpacity")
        self.status_fade_animation.setDuration(400)
        self.status_fade_animation.setEasingCurve(QEasingCurve.InOutQuad)
        self.status_hide_timer = QTimer(self)
        self.status_hide_timer.setSingleShot(True)
        self.status_hide_timer.timeout.connect(self._hide_status_bar)

        # Store last frame size and quality for adaptive bandwidth
        self.last_frame_size = 0
        self.jpeg_quality = 70 # Initial JPEG quality for server
        self.frame_rate_limit = 15 # Target FPS for server streaming

        # Initial button states
        self._update_button_states()

    def _get_local_ip(self):
        """Attempts to get the local IP address."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Doesn't actually connect, just used to get the IP
            s.connect(('10.255.255.255', 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = '127.0.0.1' # Fallback to localhost
        finally:
            s.close()
        return IP

    def _update_button_states(self):
        self.start_server_button.setEnabled(not self.is_server_running and not self.is_client_connected)
        self.stop_server_button.setEnabled(self.is_server_running)
        self.start_client_button.setEnabled(not self.is_client_connected and not self.is_server_running)
        self.stop_client_button.setEnabled(self.is_client_connected)
        
        # New: Toggle visibility of IP input and display label
        self.ip_input.setVisible(not self.is_server_running)
        self.server_ip_display_label.setVisible(self.is_server_running)
        self.ip_input.setEnabled(not self.is_server_running and not self.is_client_connected) # Ensure input is disabled when server is running

    def update_status(self, message, type='info'):
        color_map = {
            'info': '#E2E8F0',    # Light gray for general info
            'success': '#38A169', # Green for success
            'error': '#E53E3E'    # Red for errors
        }
        self.status_bar.setStyleSheet(f"""
            QStatusBar {{
                background-color: #2D3748;
                color: {color_map.get(type, '#E2E8F0')};
                font-size: 15px;
                padding: 10px;
                border-top: 1px solid #4A5568;
                border-radius: 0 0 15px 15px;
            }}
        """)
        self.status_bar.showMessage(message)

        # Start fade-in animation
        self.status_fade_animation.setStartValue(0.0)
        self.status_fade_animation.setEndValue(1.0)
        self.status_fade_animation.start()

        # Set timer to hide after a delay
        self.status_hide_timer.start(5000) # Hide after 5 seconds

    def _hide_status_bar(self):
        self.status_fade_animation.setStartValue(1.0)
        self.status_fade_animation.setEndValue(0.0)
        self.status_fade_animation.start()
        # Disconnect signal to avoid multiple connections if called rapidly
        try:
            self.status_fade_animation.finished.disconnect()
        except TypeError:
            pass # Already disconnected
        self.status_fade_animation.finished.connect(lambda: self.status_bar.showMessage(""))

    def start_server(self):
        if self.is_server_running:
            self.status_signal.message.emit("Server is already running.", 'info')
            return
        
        self.is_server_running = True
        self._update_button_states() # Update UI immediately
        self.server_ip_display_label.setText(f"Server IP: {self.local_ip}") # Ensure label shows current IP
        self.status_signal.message.emit(f"Starting server... Your IP: {self.local_ip}. Waiting for client connection...", 'info')
        
        # Start server in a new thread
        self.screen_stream_thread = threading.Thread(target=self.run_server_loop, daemon=True)
        self.screen_stream_thread.start()

    def run_server_loop(self):
        """Main server loop for accepting connections and streaming."""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # Allow reuse of address
            self.server_socket.settimeout(1.0) # Set a timeout for accept to allow checking is_server_running flag
            self.server_socket.bind(('0.0.0.0', 9999))
            self.server_socket.listen(1)
            self.status_signal.message.emit(f"Server listening on {self.local_ip}:9999", 'info')

            while self.is_server_running:
                try:
                    self.server_connection, self.server_address = self.server_socket.accept()
                    self.status_signal.message.emit(f"Client connected from {self.server_address[0]}:{self.server_address[1]}", 'success')
                    self.is_streaming = True # Indicate active streaming to a client
                    
                    # Start thread to handle client input (mouse/keyboard)
                    self.input_handler_thread = threading.Thread(target=self.handle_client_input, args=(self.server_connection,), daemon=True)
                    self.input_handler_thread.start()

                    try:
                        last_frame_time = time.time()
                        while self.is_streaming and self.is_server_running:
                            # Frame rate limiting
                            current_time = time.time()
                            time_to_sleep = (1.0 / self.frame_rate_limit) - (current_time - last_frame_time)
                            if time_to_sleep > 0:
                                time.sleep(time_to_sleep)
                            last_frame_time = time.time()

                            screenshot = pyautogui.screenshot()
                            frame = np.array(screenshot)
                            
                            # Adaptive quality logic
                            # Target frame size range (adjust based on network conditions/desired quality)
                            target_min_size = 50000 # bytes
                            target_max_size = 150000 # bytes

                            if self.last_frame_size > target_max_size:
                                self.jpeg_quality = max(20, self.jpeg_quality - 5)
                            elif self.last_frame_size < target_min_size and self.jpeg_quality < 90:
                                self.jpeg_quality = min(90, self.jpeg_quality + 5)

                            _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality])
                            data = zlib.compress(buffer)
                            size = len(data)
                            self.last_frame_size = size # Update last frame size

                            # Send frame size (8 bytes) then compressed frame data
                            self.server_connection.sendall(size.to_bytes(8, 'big') + data)
                    except (socket.error, ConnectionResetError) as e:
                        self.status_signal.message.emit(f"Server streaming error (client disconnected): {e}", 'error')
                    except Exception as e:
                        self.status_signal.message.emit(f"Server streaming general error: {e}", 'error')
                    finally:
                        self.is_streaming = False
                        if self.server_connection:
                            try:
                                self.server_connection.shutdown(socket.SHUT_RDWR)
                                self.server_connection.close()
                            except OSError:
                                pass # Socket might already be closed
                            self.server_connection = None
                        self.status_signal.message.emit("Client connection closed on server side.", 'info')
                        # Ensure input handler thread is also stopped if it's running
                        if self.input_handler_thread and self.input_handler_thread.is_alive():
                            # The input handler thread will naturally exit when its recv fails
                            pass 
                except socket.timeout:
                    # Timeout on accept, continue loop to check is_server_running flag
                    continue
                except OSError as e:
                    if self.is_server_running: # Only report if we intended to be running
                        self.status_signal.message.emit(f"Server socket error: {e}", 'error')
                    break # Exit loop if main server socket has issues
                except Exception as e:
                    self.status_signal.message.emit(f"Unhandled server loop error: {e}", 'error')
                    break
        except Exception as e:
            self.status_signal.message.emit(f"Failed to start server: {e}. Check if port 9999 is free or already in use.", 'error')
        finally:
            self.is_server_running = False
            if self.server_socket:
                try:
                    self.server_socket.shutdown(socket.SHUT_RDWR)
                    self.server_socket.close()
                except OSError:
                    pass
                self.server_socket = None
            self.status_signal.message.emit("Server stopped.", 'info')
            self._update_button_states()

    def stop_server(self):
        if not self.is_server_running:
            self.status_signal.message.emit("Server is not running.", 'info')
            return
        
        self.is_server_running = False # Set flag to stop the server loop
        self.is_streaming = False # Ensure streaming also stops if active
        self.status_signal.message.emit("Stopping server...", 'info')
        
        # Attempt to close sockets to unblock threads
        if self.server_connection:
            try:
                self.server_connection.shutdown(socket.SHUT_RDWR)
                self.server_connection.close()
            except OSError:
                pass
            self.server_connection = None
        if self.server_socket:
            try:
                self.server_socket.shutdown(socket.SHUT_RDWR)
                self.server_socket.close()
            except OSError:
                pass
            self.server_socket = None
        
        # Wait for threads to finish (optional, but good for clean shutdown)
        if self.screen_stream_thread and self.screen_stream_thread.is_alive():
            self.screen_stream_thread.join(timeout=2.0)
        if self.input_handler_thread and self.input_handler_thread.is_alive():
            self.input_handler_thread.join(timeout=2.0)

        self._update_button_states()


    def handle_client_input(self, conn):
        """Thread to listen for and process client input commands."""
        try:
            while self.is_streaming and self.is_server_running:
                # Read 4 bytes for command length
                command_len_bytes = self._recv_all(conn, 4)
                if not command_len_bytes:
                    break # Connection closed
                command_len = int.from_bytes(command_len_bytes, 'big')
                
                # Read the command data
                command_data = self._recv_all(conn, command_len)
                if not command_data:
                    break # Connection closed

                # Deserialize and execute command
                try:
                    cmd_parts = command_data.decode('utf-8').split('|')
                    cmd_type = cmd_parts[0]
                    
                    if cmd_type == "MOUSE_MOVE" and len(cmd_parts) == 3:
                        x, y = int(cmd_parts[1]), int(cmd_parts[2])
                        pyautogui.moveTo(x, y, duration=0)
                    elif cmd_type == "MOUSE_CLICK" and len(cmd_parts) == 4:
                        button, x, y = cmd_parts[1], int(cmd_parts[2]), int(cmd_parts[3])
                        pyautogui.click(x=x, y=y, button=button)
                    elif cmd_type == "MOUSE_DOWN" and len(cmd_parts) == 4:
                        button, x, y = cmd_parts[1], int(cmd_parts[2]), int(cmd_parts[3])
                        pyautogui.mouseDown(x=x, y=y, button=button)
                    elif cmd_type == "MOUSE_UP" and len(cmd_parts) == 4:
                        button, x, y = cmd_parts[1], int(cmd_parts[2]), int(cmd_parts[3])
                        pyautogui.mouseUp(x=x, y=y, button=button)
                    elif cmd_type == "MOUSE_SCROLL" and len(cmd_parts) == 2:
                        clicks = int(cmd_parts[1])
                        pyautogui.scroll(clicks)
                    elif cmd_type == "KEY_DOWN" and len(cmd_parts) == 2:
                        key = cmd_parts[1]
                        pyautogui.keyDown(key)
                    elif cmd_type == "KEY_UP" and len(cmd_parts) == 2:
                        key = cmd_parts[1]
                        pyautogui.keyUp(key)
                    # Add more commands as needed (e.g., drag, hotkeys)
                except IndexError:
                    self.status_signal.message.emit("Server: Received malformed command.", 'error')
                except ValueError:
                    self.status_signal.message.emit("Server: Received invalid command data.", 'error')
                except Exception as cmd_e:
                    self.status_signal.message.emit(f"Server: Error processing command: {cmd_e}", 'error')

        except (socket.error, ConnectionResetError) as e:
            self.status_signal.message.emit(f"Server input handler connection error: {e}", 'error')
        except Exception as e:
            self.status_signal.message.emit(f"Server input handler general error: {e}", 'error')
        finally:
            self.status_signal.message.emit("Client input handler stopped.", 'info')
            self.is_streaming = False # Ensure streaming also stops if input fails

    def _recv_all(self, sock, n):
        """Helper function to ensure all bytes are received from a socket."""
        data = b''
        while len(data) < n:
            packet = sock.recv(n - len(data))
            if not packet:
                return None # Connection closed or error
            data += packet
        return data

    def start_client(self):
        if self.is_client_connected:
            self.status_signal.message.emit("Client is already connected.", 'info')
            return
        if self.is_server_running:
            self.status_signal.message.emit("Cannot run client while server is active.", 'error')
            return

        server_ip = self.ip_input.text().strip()
        if not server_ip:
            self.status_signal.message.emit("Please enter a valid server IP.", 'error')
            return

        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.connect((server_ip, 9999))
            self.is_client_connected = True
            self.is_streaming = True # Client is now actively receiving stream
            self._update_button_states()
            self.status_signal.message.emit("Connected to server. Streaming...", 'success')
            self.image_label.setText("") # Clear "Waiting for connection" text

            # Start a separate thread for receiving frames
            self.client_receive_thread = threading.Thread(target=self._client_receive_loop, daemon=True)
            self.client_receive_thread.start()

            # Start a QTimer to update the UI with the latest frame from the buffer
            self.client_ui_update_timer.start(30) # Update UI approx 30 FPS

        except ConnectionRefusedError:
            self.status_signal.message.emit(f"Connection refused to {server_ip}:9999. Is the server running?", 'error')
            self.stop_client_session()
        except socket.timeout:
            self.status_signal.message.emit(f"Connection timed out to {server_ip}:9999.", 'error')
            self.stop_client_session()
        except socket.gaierror:
            self.status_signal.message.emit(f"Invalid server IP address: {server_ip}", 'error')
            self.stop_client_session()
        except Exception as e:
            self.status_signal.message.emit(f"Client connection failed: {e}", 'error')
            self.stop_client_session()

    def _client_receive_loop(self):
        """Thread to continuously receive frames from the server."""
        try:
            while self.is_client_connected and self.is_streaming:
                # Read 8 bytes for frame size
                size_bytes = self._recv_all(self.client_socket, 8)
                if not size_bytes:
                    self.status_signal.message.emit("Server disconnected while receiving frame size.", 'error')
                    break # Connection closed
                size = int.from_bytes(size_bytes, 'big')

                data = self._recv_all(self.client_socket, size)
                if not data:
                    self.status_signal.message.emit("Server disconnected while receiving frame data.", 'error')
                    break # Connection closed
                
                # Store the latest frame data in a thread-safe manner
                with self.latest_frame_lock:
                    self.latest_frame_data = data
        except (socket.error, ConnectionResetError) as ce:
            self.status_signal.message.emit(f"Client receive error: {ce}", 'error')
        except Exception as e:
            self.status_signal.message.emit(f"General client receive loop error: {e}", 'error')
        finally:
            self.is_streaming = False # Stop streaming flag
            self.status_signal.message.emit("Client receive loop stopped.", 'info')
            self.stop_client_session() # Ensure full session cleanup

    def _update_image_label_from_buffer(self):
        """Updates the QLabel with the latest frame from the buffer."""
        if not self.is_client_connected:
            return

        frame_data = None
        with self.latest_frame_lock:
            if self.latest_frame_data:
                frame_data = self.latest_frame_data
                self.latest_frame_data = None # Clear buffer after use

        if frame_data:
            try:
                frame = zlib.decompress(frame_data)
                frame = cv2.imdecode(np.frombuffer(frame, np.uint8), cv2.IMREAD_COLOR)
                
                if frame is None:
                    self.status_signal.message.emit("Could not decode image frame. Corrupted data?", 'error')
                    return

                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame.shape
                bytes_per_line = ch * w
                qimg = QImage(frame.data, w, h, bytes_per_line, QImage.Format_RGB888)
                
                # Scale pixmap to fit the image_label, maintaining aspect ratio
                pixmap = QPixmap.fromImage(qimg)
                scaled_pixmap = pixmap.scaled(self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                
                self.image_label.setPixmap(scaled_pixmap)
            except Exception as e:
                self.status_signal.message.emit(f"Error processing/displaying frame: {e}", 'error')
                self.stop_client_session()


    def send_input_events(self, event_type, *args):
        if not self.client_socket or not self.is_client_connected:
            return

        try:
            command = f"{event_type}"
            if event_type.startswith("MOUSE"):
                # Get the currently displayed pixmap and its original dimensions
                current_pixmap = self.image_label.pixmap()
                if current_pixmap is None:
                    # Cannot scale if no image is displayed yet
                    return 

                # Get the original dimensions of the image that was sent from the server
                # This is crucial for accurate coordinate mapping.
                # If the server sends a 1920x1080 image, and client displays it scaled,
                # mouse events need to be mapped back to 1920x1080.
                # For simplicity, we assume the original image size is what was captured by pyautogui.screenshot()
                # A more robust solution would be for the server to send its screen resolution on connection.
                # For now, we'll use the pixmap's original size as the target resolution.
                original_width = current_pixmap.width()
                original_height = current_pixmap.height()
                
                # Get the actual rectangle where the pixmap is drawn within the QLabel
                # This accounts for Qt.KeepAspectRatio and potential black bars
                label_rect = self.image_label.contentsRect()
                pixmap_scaled_size = current_pixmap.size().scaled(label_rect.size(), Qt.KeepAspectRatio)

                offset_x = (label_rect.width() - pixmap_scaled_size.width()) / 2
                offset_y = (label_rect.height() - pixmap_scaled_size.height()) / 2

                # Calculate scaling factors from displayed scaled image to original image
                scale_x = original_width / pixmap_scaled_size.width()
                scale_y = original_height / pixmap_scaled_size.height()

                if event_type == "MOUSE_MOVE" or event_type == "MOUSE_DOWN" or event_type == "MOUSE_UP":
                    x_label, y_label = args[0], args[1]
                    
                    # Convert QLabel coordinates to original pixmap coordinates
                    x_original = int((x_label - offset_x) * scale_x)
                    y_original = int((y_label - offset_y) * scale_y)

                    # Clamp coordinates to ensure they are within the original image bounds
                    x_original = max(0, min(x_original, original_width - 1))
                    y_original = max(0, min(y_original, original_height - 1))

                    command += f"|{x_original}|{y_original}"
                    if len(args) > 2: # For mouse clicks/down/up, button is also passed
                        command += f"|{args[2]}" # button
                elif event_type == "MOUSE_SCROLL":
                    command += f"|{args[0]}" # clicks
            elif event_type.startswith("KEY"):
                command += f"|{args[0]}" # key
            
            command_bytes = command.encode('utf-8')
            command_len = len(command_bytes)
            
            # Send length first (4 bytes), then data
            self.client_socket.sendall(command_len.to_bytes(4, 'big') + command_bytes)

        except (socket.error, ConnectionResetError) as e:
            self.status_signal.message.emit(f"Error sending input event: {e}. Disconnecting client.", 'error')
            self.stop_client_session()
        except Exception as e:
            # print(f"Warning: Error in send_input_events: {e}") # For debugging, can be noisy
            pass # Suppress minor errors, as frequent input events might generate them

    # Event filter to capture mouse events on image_label
    def eventFilter(self, obj, event):
        if obj == self.image_label and self.is_client_connected:
            if event.type() == QEvent.MouseButtonPress:
                self.send_input_events("MOUSE_DOWN", event.position().x(), event.position().y(), self._map_qt_button(event.button()))
                return True
            elif event.type() == QEvent.MouseButtonRelease:
                self.send_input_events("MOUSE_UP", event.position().x(), event.position().y(), self._map_qt_button(event.button()))
                return True
            elif event.type() == QEvent.MouseMove:
                # Send mouse move events for both simple moves and drags
                self.send_input_events("MOUSE_MOVE", event.position().x(), event.position().y())
                return True
            elif event.type() == QEvent.Wheel:
                degrees = event.angleDelta().y() / 8 # Standard Qt wheel delta is 8*degrees
                # PyAutoGUI scroll units are usually 15 degrees per "click"
                self.send_input_events("MOUSE_SCROLL", int(degrees / 15))
                return True
        return super().eventFilter(obj, event)

    def _map_qt_button(self, qt_button):
        if qt_button == Qt.LeftButton:
            return "left"
        elif qt_button == Qt.RightButton:
            return "right"
        elif qt_button == Qt.MiddleButton:
            return "middle"
        return "left" # Default or raise error for unhandled

    # Override key event handlers for the main window (client mode)
    def keyPressEvent(self, event: QKeyEvent):
        if self.is_client_connected:
            # Filter out auto-repeat events to prevent multiple key down/up for a single press
            if not event.isAutoRepeat():
                key_name = self._map_qt_key_to_pyautogui(event.key())
                if key_name:
                    self.send_input_events("KEY_DOWN", key_name)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if self.is_client_connected:
            if not event.isAutoRepeat():
                key_name = self._map_qt_key_to_pyautogui(event.key())
                if key_name:
                    self.send_input_events("KEY_UP", key_name)
        super().keyReleaseEvent(event)

    def _map_qt_key_to_pyautogui(self, qt_key):
        # Comprehensive mapping of Qt keys to PyAutoGUI key names
        # This list can be expanded as needed for more special keys
        key_map = {
            Qt.Key_Return: 'enter', Qt.Key_Enter: 'enter', Qt.Key_Space: 'space',
            Qt.Key_Backspace: 'backspace', Qt.Key_Tab: 'tab', Qt.Key_Escape: 'esc',
            Qt.Key_Up: 'up', Qt.Key_Down: 'down', Qt.Key_Left: 'left', Qt.Key_Right: 'right',
            Qt.Key_Shift: 'shift', Qt.Key_Control: 'ctrl', Qt.Key_Alt: 'alt',
            Qt.Key_Meta: 'win', # Windows key
            Qt.Key_CapsLock: 'capslock', Qt.Key_NumLock: 'numlock', Qt.Key_ScrollLock: 'scrolllock',
            Qt.Key_Insert: 'insert', Qt.Key_Delete: 'delete', Qt.Key_Home: 'home',
            Qt.Key_End: 'end', Qt.Key_PageUp: 'pageup', Qt.Key_PageDown: 'pagedown',
            Qt.Key_F1: 'f1', Qt.Key_F2: 'f2', Qt.Key_F3: 'f3', Qt.Key_F4: 'f4',
            Qt.Key_F5: 'f5', Qt.Key_F6: 'f6', Qt.Key_F7: 'f7', Qt.Key_F8: 'f8',
            Qt.Key_F9: 'f9', Qt.Key_F10: 'f10', Qt.Key_F11: 'f11', Qt.Key_F12: 'f12',
            Qt.Key_Print: 'printscreen', Qt.Key_Pause: 'pause', Qt.Key_Menu: 'apps', # Context menu key
            Qt.Key_Period: '.', Qt.Key_Comma: ',', Qt.Key_Slash: '/',
            Qt.Key_Backslash: '\\', Qt.Key_Minus: '-', Qt.Key_Equal: '=',
            Qt.Key_BracketLeft: '[', Qt.Key_BracketRight: ']', Qt.Key_Semicolon: ';',
            Qt.Key_Apostrophe: "'", Qt.Key_Grave: '`', # Backtick
            Qt.Key_QuoteDbl: '"', Qt.Key_Plus: '+', Qt.Key_Underscore: '_',
            Qt.Key_Asterisk: '*', Qt.Key_Ampersand: '&', Qt.Key_ParenLeft: '(',
            Qt.Key_ParenRight: ')', Qt.Key_Exclam: '!', Qt.Key_At: '@',
            Qt.Key_NumberSign: '#', Qt.Key_Dollar: '$', Qt.Key_Percent: '%',
            Qt.Key_Caret: '^', Qt.Key_Colon: ':', Qt.Key_Less: '<',
            Qt.Key_Greater: '>', Qt.Key_Question: '?', Qt.Key_Bar: '|',
            Qt.Key_Tilde: '~', Qt.Key_BraceLeft: '{', Qt.Key_BraceRight: '}',
            # Numpad keys
            Qt.Key_Numpad0: 'num0', Qt.Key_Numpad1: 'num1', Qt.Key_Numpad2: 'num2',
            Qt.Key_Numpad3: 'num3', Qt.Key_Numpad4: 'num4', Qt.Key_Numpad5: 'num5',
            Qt.Key_Numpad6: 'num6', Qt.Key_Numpad7: 'num7', Qt.Key_Numpad8: 'num8',
            Qt.Key_Numpad9: 'num9', Qt.Key_NumpadAdd: 'numadd', Qt.Key_NumpadSubtract: 'numsubtract',
            Qt.Key_NumpadMultiply: 'nummultiply', Qt.Key_NumpadDivide: 'numdivide',
            Qt.Key_NumpadDecimal: 'numdecimal', Qt.Key_NumpadEnter: 'enter', # Numpad enter is just 'enter'
        }
        
        # Handle digits and letters directly as they map simply
        if Qt.Key_0 <= qt_key <= Qt.Key_9:
            return chr(qt_key)
        if Qt.Key_A <= qt_key <= Qt.Key_Z:
            return chr(qt_key).lower() # PyAutoGUI uses lowercase for letters

        return key_map.get(qt_key, None) # Return None if not mapped

    def stop_client_session(self):
        if not self.is_client_connected:
            return

        self.client_ui_update_timer.stop() # Stop UI update timer
        self.is_client_connected = False
        self.is_streaming = False # Stop client receiving loop

        if self.client_socket:
            try:
                # Attempt graceful shutdown before closing
                self.client_socket.shutdown(socket.SHUT_RDWR)
                self.client_socket.close()
            except OSError as e:
                self.status_signal.message.emit(f"Error closing client socket: {e}", 'error')
            self.client_socket = None
        
        # Wait for client receive thread to finish
        if self.client_receive_thread and self.client_receive_thread.is_alive():
            self.client_receive_thread.join(timeout=2.0)

        self.image_label.clear() # Clear existing image
        self.image_label.setText("Connection lost or stream ended. Please reconnect.")
        self.status_signal.message.emit("Client session ended.", 'info')
        self._update_button_states()

    def closeEvent(self, event):
        # Ensure all sockets are closed and threads are stopped on application exit
        self.stop_client_session() # Stop client if active
        self.stop_server() # Stop server if active (this will also join server threads)
        
        super().closeEvent(event)

if __name__ == '__main__':
    # Configure pyautogui for remote control
    try:
        pyautogui.FAILSAFE = False # IMPORTANT: Disables the failsafe. Use with caution!
                                  # If you lose control, move mouse to top-left corner to stop.
                                  # For a remote desktop, you usually want this off.
        pyautogui.PAUSE = 0.0 # No pause between pyautogui commands for responsiveness
    except Exception as e:
        print(f"Warning: Could not configure pyautogui: {e}")
        print("This might happen if running in a headless environment without a display.")

    app = QApplication(sys.argv)
    window = DJRemoteDesktop()
    window.show()
    sys.exit(app.exec())
