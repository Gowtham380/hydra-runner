import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import './index.css';
import { registerSwMesh } from './utils/swStreamer';

// Auto-Register ServiceWorker Mesh Streamer on startup
registerSwMesh();

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
