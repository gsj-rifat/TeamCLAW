const express = require('express');
const app = express();

// Get port from environment variable or use 3000 for local development
const PORT = process.env.PORT || 3000;

// Middleware to parse JSON requests
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Root endpoint - for testing
app.get('/', (req, res) => {
  res.json({
    message: 'Webhook server is running!',
    status: 'success',
    timestamp: new Date().toISOString()
  });
});

// Main webhook endpoint - this is where commands/payloads will be sent
app.post('/webhook', (req, res) => {
  console.log('Received webhook:', req.body);

  // Process the incoming data here
  // For now, just echo it back
  res.json({
    message: 'Webhook received successfully',
    received_data: req.body,
    timestamp: new Date().toISOString()
  });
});

// Additional endpoint for commands
app.post('/commands', (req, res) => {
  console.log('Received command:', req.body);

  res.json({
    message: 'Command processed',
    command_data: req.body,
    timestamp: new Date().toISOString()
  });
});

// Start the server
app.listen(PORT, () => {
  console.log(`Server is running on port ${PORT}`);
});