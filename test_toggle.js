const fs = require('fs');
const jsdom = require('jsdom');
const { JSDOM } = jsdom;

const html = fs.readFileSync('frontend/index.html', 'utf8');
const dom = new JSDOM(html, { runScripts: "dangerously", url: "http://localhost:8765/" });

const window = dom.window;
const document = window.document;

const scriptApi = fs.readFileSync('frontend/js/api.js', 'utf8');
const scriptApp = fs.readFileSync('frontend/js/app.js', 'utf8');

window.eval(scriptApi);
window.eval(scriptApp);

window.fetch = async function() { throw new Error("Network error"); };

(async () => {
  await window.toggleDirectoryMode("Bangumi", true);
  console.log(document.getElementById('toast-container').innerHTML);
})();
