// public/app.js
let ws;
let remotes = [];

// Connect to WebSocket
function connectWebSocket() {
  ws = new WebSocket(`ws://${window.location.host}`);
  
  ws.onopen = () => {
    console.log('WebSocket connected');
  };
  
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    if (data.type === 'irData') {
      handleCapturedIRData(data.data);
    }
  };
  
  ws.onclose = () => {
    console.log('WebSocket disconnected. Reconnecting...');
    setTimeout(connectWebSocket, 2000);
  };
}

// Load remotes from the server
async function loadRemotes() {
  const response = await fetch('/api/remotes');
  remotes = await response.json();
  updateUI();
}

// Add a new remote
async function addRemote() {
  const remoteName = document.getElementById('remoteName').value.trim();
  if (!remoteName) return;
  
  const response = await fetch('/api/remotes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: remoteName, buttons: [] })
  });
  
  if (response.ok) {
    document.getElementById('remoteName').value = '';
    await loadRemotes();
  }
}

// Capture IR button
function captureIR() {
  const remoteName = document.getElementById('remoteSelect').value;
  const buttonName = document.getElementById('buttonName').value.trim();
  
  if (!remoteName || !buttonName) {
    alert('Please select a remote and enter a button name');
    return;
  }
  
  document.getElementById('captureStatus').textContent = 'Point remote at ESP32 and press button...';
  
  // Request capture via WebSocket
  ws.send(JSON.stringify({ type: 'captureRequest' }));
}

// Handle captured IR data
async function handleCapturedIRData(irData) {
  const remoteName = document.getElementById('remoteSelect').value;
  const buttonName = document.getElementById('buttonName').value.trim();
  
  const buttonData = {
    name: buttonName,
    protocol: irData.protocol,
    address: irData.address,
    command: irData.command,
    bits: irData.bits,
    timestamp: new Date().toISOString()
  };
  
  const response = await fetch('/api/buttons', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ remoteName, buttonData })
  });
  
  if (response.ok) {
    document.getElementById('captureStatus').textContent = `Button "${buttonName}" captured successfully!`;
    document.getElementById('buttonName').value = '';
    await loadRemotes();
  }
}

// Deploy selected remotes to ESP32
async function deployToESP32() {
  const checkboxes = document.querySelectorAll('#deployList input[type="checkbox"]:checked');
  const remoteNames = Array.from(checkboxes).map(cb => cb.value);
  
  if (remoteNames.length === 0) {
    alert('Please select at least one remote to deploy');
    return;
  }
  
  const response = await fetch('/api/deploy', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ remoteNames })
  });
  
  if (response.ok) {
    alert('Remotes deployed to ESP32 successfully!');
  } else {
    alert('Failed to deploy remotes');
  }
}

// Update the UI with current data
function updateUI() {
  // Update remote select dropdown
  const remoteSelect = document.getElementById('remoteSelect');
  remoteSelect.innerHTML = '';
  
  remotes.forEach(remote => {
    const option = document.createElement('option');
    option.value = remote.name;
    option.textContent = remote.name;
    remoteSelect.appendChild(option);
  });
  
  // Update remotes list
  const remotesList = document.getElementById('remotesList');
  remotesList.innerHTML = '';
  
  remotes.forEach(remote => {
    const remoteDiv = document.createElement('div');
    remoteDiv.className = 'remote-item';
    
    remoteDiv.innerHTML = `
      <h3>${remote.name}</h3>
      <div class="buttons-list">
        ${remote.buttons ? remote.buttons.map(button => `
          <div class="button-item">
            <span>${button.name}</span>
            <span class="button-details">
              Protocol: ${button.protocol}, 
              Command: 0x${button.command.toString(16).toUpperCase()}
            </span>
          </div>
        `).join('') : 'No buttons mapped yet'}
      </div>
    `;
    
    remotesList.appendChild(remoteDiv);
  });
  
  // Update deploy list
  const deployList = document.getElementById('deployList');
  deployList.innerHTML = '';
  
  remotes.forEach(remote => {
    const deployItem = document.createElement('div');
    deployItem.className = 'deploy-item';
    
    deployItem.innerHTML = `
      <input type="checkbox" id="deploy-${remote.name}" value="${remote.name}">
      <label for="deploy-${remote.name}">${remote.name} (${remote.buttons ? remote.buttons.length : 0} buttons)</label>
    `;
    
    deployList.appendChild(deployItem);
  });
}

// Initialize
window.addEventListener('DOMContentLoaded', () => {
  connectWebSocket();
  loadRemotes();
  
  document.getElementById('addRemote').addEventListener('click', addRemote);
  document.getElementById('captureButton').addEventListener('click', captureIR);
  document.getElementById('deployButton').addEventListener('click', deployToESP32);
});