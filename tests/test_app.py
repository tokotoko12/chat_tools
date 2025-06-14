import unittest
import sys
import os

# Add the parent directory to sys.path to allow imports from app.py
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, socketio, chat_messages # Import necessary components

class BasicTests(unittest.TestCase):

    def setUp(self):
        """Set up test client and other test variables."""
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test_secret_key' # Use a consistent test key
        app.config['WTF_CSRF_ENABLED'] = False # Disable CSRF for form tests if applicable
        self.client = app.test_client()

        # Clear chat messages before each test that might interact with them
        chat_messages.clear()
        # print("App context for test client:", self.client.application) # For debugging

    def tearDown(self):
        """Tear down test variables."""
        pass # Nothing specific to tear down for now

    # ============== Login/Logout Tests ==============
    def test_01_login_page_loads(self):
        """Test that the login page loads correctly."""
        response = self.client.get('/login')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Login', response.data)

    def test_02_successful_login(self):
        """Test successful login with correct credentials."""
        response = self.client.post('/login', data=dict(
            username='admin',
            password='password'
        ), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Chat Room (User: admin)', response.data)
        # Check that session is set
        with self.client.session_transaction() as sess:
            self.assertEqual(sess.get('username'), 'admin')

    def test_03_failed_login_wrong_password(self):
        """Test failed login with incorrect password."""
        response = self.client.post('/login', data=dict(
            username='admin',
            password='wrongpassword'
        ), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Invalid Credentials. Please try again.', response.data)
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get('username'))

    def test_04_failed_login_wrong_username(self):
        """Test failed login with incorrect username."""
        response = self.client.post('/login', data=dict(
            username='wronguser',
            password='password'
        ), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Invalid Credentials. Please try again.', response.data)
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get('username'))

    def test_05_logout(self):
        """Test logout functionality."""
        # First, log in
        self.client.post('/login', data=dict(
            username='admin',
            password='password'
        ), follow_redirects=True)

        # Check session is set
        with self.client.session_transaction() as sess:
            self.assertIsNotNone(sess.get('username'))

        # Then, logout
        response = self.client.get('/logout', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Login', response.data) # Should be redirected to login page
        with self.client.session_transaction() as sess:
            self.assertIsNone(sess.get('username'))

    def test_06_chat_page_requires_login(self):
        """Test that accessing /chat directly redirects to login if not logged in."""
        response = self.client.get('/chat', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Login', response.data) # Should redirect to login

    def test_07_index_redirects_to_login_if_not_logged_in(self):
        """Test that the index page / redirects to login if not logged in."""
        response = self.client.get('/', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Login', response.data)

    def test_08_index_redirects_to_chat_if_logged_in(self):
        """Test that the index page / redirects to chat if logged in."""
        self.client.post('/login', data=dict(username='admin', password='password'), follow_redirects=True)
        response = self.client.get('/', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Chat Room (User: admin)', response.data)

    # ============== Chat Functionality Tests (Conceptual) ==============
    # These tests are more complex with SocketIO and a simple test client.
    # We will primarily test the effect on server-side state (chat_messages list).

    def test_09_send_message_stores_message_after_login(self):
        """Test that sending a message (mocked) stores it in chat_messages."""
        # Log in first
        with self.client as c: # Use 'with' to ensure session persistence for SocketIO context
            c.post('/login', data=dict(username='admin', password='password'), follow_redirects=True)
            # At this point, session['username'] should be 'admin'

            # Simulate a SocketIO client connecting and sending a message.
            # This requires the test client to have the session context.
            # We directly call the handler as if a message was received.
            # For full SocketIO testing, flask_socketio.test_client is needed.

            # Get a SocketIO test client
            sio_test_client = socketio.test_client(app, flask_test_client=c)
            self.assertTrue(sio_test_client.is_connected())

            # Simulate sending a message
            sio_test_client.emit('send_message', {'message': 'Hello from test!'})

            self.assertEqual(len(chat_messages), 1)
            self.assertEqual(chat_messages[0]['user'], 'admin')
            self.assertEqual(chat_messages[0]['message'], 'Hello from test!')
            sio_test_client.disconnect()

    def test_10_new_client_receives_historical_messages_after_login(self):
        """Test that a new client receives historical messages on connect."""
         # Pre-populate some messages by one user
        with self.client as c1:
            c1.post('/login', data=dict(username='user1', password='password'), follow_redirects=True)
            sio_test_client1 = socketio.test_client(app, flask_test_client=c1)
            self.assertTrue(sio_test_client1.is_connected()) # Ensure connect handler runs for user1
            sio_test_client1.emit('send_message', {'message': 'Message 1 by user1'})
            sio_test_client1.emit('send_message', {'message': 'Message 2 by user1'})
            sio_test_client1.disconnect() # Disconnect user1

        self.assertEqual(len(chat_messages), 2) # Verify messages are stored

        # Now, a new user ('user2') logs in and connects
        with self.client as c2:
            c2.post('/login', data=dict(username='admin', password='password'), follow_redirects=True) # 'admin' as user2
            sio_test_client2 = socketio.test_client(app, flask_test_client=c2)
            self.assertTrue(sio_test_client2.is_connected()) # Connects and should trigger 'load_messages'

            # Check received messages by sio_test_client2
            received = sio_test_client2.get_received()

            # The first event for a new connection might be the connection acknowledgment itself,
            # then 'load_messages'. Let's find 'load_messages'.
            loaded_messages_event = None
            for event in received:
                if event['name'] == 'load_messages':
                    loaded_messages_event = event
                    break

            self.assertIsNotNone(loaded_messages_event, "Client should have received 'load_messages' event")
            self.assertEqual(len(loaded_messages_event['args'][0]), 2)
            self.assertEqual(loaded_messages_event['args'][0][0]['message'], 'Message 1 by user1')
            self.assertEqual(loaded_messages_event['args'][0][1]['message'], 'Message 2 by user1')
            sio_test_client2.disconnect()

if __name__ == '__main__':
    unittest.main()
