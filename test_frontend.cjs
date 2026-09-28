const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {test} = require('node:test');

test('add form blocks repeat submissions and allows retry after failure', async () => {
  const html = fs.readFileSync(`${__dirname}/frontend/index.html`, 'utf8');
  const handler = html.slice(html.indexOf('let addingApplication=false;'), html.indexOf('loadUser(); load();'));
  assert.ok(handler.length > 0);
  const button = {disabled:false, textContent:'Add application'};
  let requests = 0, resets = 0, resolveRequest, rejectRequest;
  const form = {querySelector:()=>button, reset:()=>resets++};
  vm.runInNewContext(handler, {
    form,
    document:{getElementById:()=>({value:'Example'})},
    modal:{classList:{remove:()=>{}}},
    load:async()=>{},
    checkedFetch:()=>{
      requests++;
      return new Promise((resolve,reject)=>{resolveRequest=resolve;rejectRequest=reject;});
    },
  });
  const event = {preventDefault(){}};
  const first = form.onsubmit(event);
  await form.onsubmit(event);
  assert.equal(requests, 1);
  assert.equal(button.disabled, true);
  resolveRequest();
  await first;
  assert.equal(resets, 1);
  assert.equal(button.disabled, false);
  const failed = form.onsubmit(event);
  rejectRequest(new Error('Save failed'));
  await assert.rejects(failed, /Save failed/);
  assert.equal(resets, 1, 'failed save preserves the entered values');
  assert.equal(button.disabled, false);
  const retry = form.onsubmit(event);
  resolveRequest();
  await retry;
  assert.equal(requests, 3);
  assert.equal(resets, 2);
});
