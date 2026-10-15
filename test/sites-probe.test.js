const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync("sites/phone-probe/src/pkjs/index.js", "utf8");
function start() {
  const requests=[], messages=[], logs=[], events={};
  function XHR(){this.headers={};requests.push(this);}
  XHR.prototype.open=function(method,url){this.method=method;this.url=url;};
  XHR.prototype.setRequestHeader=function(k,v){this.headers[k]=v;};
  XHR.prototype.send=function(){};
  vm.runInNewContext(source, {XMLHttpRequest:XHR, Pebble:{addEventListener:(name,f)=>events[name]=f,sendAppMessage:(d,done)=>{messages.push(d);done();}}, console:{log:s=>logs.push(s)}, setTimeout:f=>f()});
  events.ready();
  return {requests,messages,logs,events};
}
function reply(x,status,body){x.status=status;x.responseText=body;x.onload();}
test("Sites diagnostic reports gate status without a service credential",()=>{
  const s=start();
  reply(s.requests[0],401,"<html>Sign in</html>");
  reply(s.requests[1],401,"<html>Sign in</html>");
  assert.match(s.messages.at(-1).SUMMARY,/Sign-in required/);
  assert.deepEqual(s.requests[0].headers,{});
  assert.equal(s.requests[1].headers.Authorization,"Bearer synthetic-pebble-view-token");
  assert.ok(s.requests.every(x=>Object.keys(x.headers).every(k=>k==="Authorization")));
  assert.ok(s.requests.every(x=>x.withCredentials===true));
  assert.ok(s.messages.every(x=>x.SUMMARY.length<=190));
});
test("network failure is not reported as a proven sign-in rejection",()=>{
  const s=start();
  s.requests[0].onerror();
  s.requests[0].ontimeout();
  assert.equal(s.requests.length,2);
  s.requests[1].onerror();
  assert.match(s.messages.at(-1).SUMMARY,/Network\/permission/);
  assert.equal(s.logs.length,1);
});
test("only the expected JSON marker counts as a successful data response",()=>{
  const s=start();
  reply(s.requests[0],200,'{"kind":"pebble-hood-sites-probe"}');
  reply(s.requests[1],200,'{"kind":"different"}');
  assert.match(s.messages.at(-1).SUMMARY,/JSON reached/);
  assert.equal(JSON.parse(s.logs[0].split("SITES_TEST_RESULT ")[1]).view_token.marker,false);
});
test("private Site settings uses normal sign-in and reruns after the webview closes",()=>{
  const s=start();
  reply(s.requests[0],401,"sign in");
  reply(s.requests[1],401,"sign in");
  s.events.webviewclosed({response:"sites-cookie-probe"});
  reply(s.requests[2],401,"sign in");
  reply(s.requests[3],401,"sign in");
  assert.equal(JSON.parse(s.logs[1].split("SITES_TEST_RESULT ")[1]).phase,"after_chatgpt_signin");
});
test("sign-in return during an existing request queues a distinct follow-up check",()=>{
  const s=start();
  s.events.webviewclosed({response:"sites-cookie-probe"});
  assert.equal(s.requests.length,1);
  reply(s.requests[0],401,"sign in");
  reply(s.requests[1],401,"sign in");
  assert.equal(JSON.parse(s.logs[0].split("SITES_TEST_RESULT ")[1]).phase,"baseline");
  reply(s.requests[2],401,"sign in");
  reply(s.requests[3],401,"sign in");
  assert.equal(JSON.parse(s.logs[1].split("SITES_TEST_RESULT ")[1]).phase,"after_chatgpt_signin");
});
