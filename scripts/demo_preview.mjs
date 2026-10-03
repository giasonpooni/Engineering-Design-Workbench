// This launcher serves the installed Python application, with no simulated API.
import { createServer, request } from 'node:http';
// The supervised browser preview cannot resolve an external CPython interpreter.
// Start the installed Python backend on loopback:8765 first. This fixed proxy
// forwards the real service, including the session cookie and origin checks.
// It never manufactures scientific results or accepts a caller-selected host.
const server = createServer((req, res) => {
  const upstream = request({hostname: '127.0.0.1', port: 8765,
    path: req.url, method: req.method, headers: req.headers}, response => {
    res.writeHead(response.statusCode, response.headers);
    response.pipe(res);
  });
  upstream.on('error', () => {
    if (!res.headersSent) res.writeHead(502, {'Content-Type': 'application/json'});
    res.end(JSON.stringify({error: {code: 'BACKEND_UNAVAILABLE',
      message: 'Start the installed Python demo service on port 8765, then reload.'}}));
  });
  req.pipe(upstream);
});
server.listen(4173, '0.0.0.0', () => process.stdout.write('NET browser preview on port 4173\n'));
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => server.close(() => process.exit(0)));
