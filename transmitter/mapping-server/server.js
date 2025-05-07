// server.js - Run this on your PC
const express = require('express');
const http = require('http');
const WebSocket = require('ws');
const fs = require('fs');
const path = require('path');
const SerialPort = require('serialport');

const app = express();
const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

// Serve static files
app.use(express.static('public'));
app.use(express.json());

// Store for IR codes
let irCodesDB = {
  remotes: []
};

// Load existing codes from file if it exists
if (fs.existsSync('ir_codes.json')) {
  irCodesDB = JSON.parse(fs.readFileSync('ir_codes.json', 'utf8'));
}

// Set up serial connection to ESP32
let serialPort;
try {
  serialPort = new SerialPort('/dev/ttyUSB0', { baudRate: 115200 }); // Adjust port as needed
  console.log('Connected to ESP32');
} catch (error) {
  console.error('Failed to connect to ESP32:', error);
}

// WebSocket connection for real-time updates
wss.on('connection', (ws) => {
  console.log('Client connected');
  
  ws.on('message', (message) => {
    const data = JSON.parse(message);
    
    if (data.type === 'captureRequest') {
      // Forward capture request to ESP32
      serialPort.write('CAPTURE\n');
    }
  });
  
  // When receiving data from ESP32, forward to web client
  if (serialPort) {
    serialPort.on('data', (data) => {
      const dataStr = data.toString();
      if (dataStr.startsWith('IR:')) {
        ws.send(JSON.stringify({
          type: 'irData',
          data: JSON.parse(dataStr.substring(3))
        }));
      }
    });
  }
});

// API endpoints
app.get('/api/remotes', (req, res) => {
  res.json(irCodesDB.remotes);
});

app.post('/api/remotes', (req, res) => {
  const newRemote = req.body;
  irCodesDB.remotes.push(newRemote);
  saveDatabase();
  res.status(201).json(newRemote);
});

app.post('/api/buttons', (req, res) => {
  const { remoteName, buttonData } = req.body;
  
  const remote = irCodesDB.remotes.find(r => r.name === remoteName);
  if (!remote) {
    return res.status(404).json({ error: 'Remote not found' });
  }
  
  if (!remote.buttons) {
    remote.buttons = [];
  }
  
  remote.buttons.push(buttonData);
  saveDatabase();
  res.status(201).json(buttonData);
});

// Deploy selected remotes to ESP32
app.post('/api/deploy', (req, res) => {
  const { remoteNames } = req.body;
  
  // Filter only selected remotes
  const selectedRemotes = irCodesDB.remotes.filter(r => 
    remoteNames.includes(r.name)
  );
  
  // Send to ESP32
  if (serialPort) {
    const deployData = JSON.stringify({ deploy: selectedRemotes });
    serialPort.write(`DEPLOY:${deployData}\n`);
    res.json({ success: true, message: 'Deployment started' });
  } else {
    res.status(500).json({ error: 'ESP32 not connected' });
  }
});

function saveDatabase() {
  fs.writeFileSync('ir_codes.json', JSON.stringify(irCodesDB, null, 2));
  console.log('Database saved');
}

// Start the server
const PORT = 3000;
server.listen(PORT, () => {
  console.log(`Server running on http://localhost:${PORT}`);
});