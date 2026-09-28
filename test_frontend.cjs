const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {test} = require('node:test');

test('status is optimistic, guarded, rolled back on failure, and retained on refresh failure', async () => {
  const html=fs.readFileSync(`${__dirname}/frontend/index.html`,'utf8');
  const code=html.slice(html.indexOf('// Keep server data separate'),html.indexOf("document.getElementById('cancel-status')"));
  const elements={'confirm-status':{},'new-status':{value:'Offer'},'request-error':{hidden:true}};
  let rendered, requests=0, resolveRequest, rejectRequest;
  const button={dataset:{id:'1'},setAttribute(){}};
  const context=vm.createContext({
    pendingStatusId:'1',loadVersion:0,
    display:items=>{rendered=items;},
    table:{querySelectorAll:()=>[button]},
    document:{getElementById:id=>elements[id]},
    statusModal:{classList:{remove(){},add(){}}},
    checkedFetch:()=>{requests++;return new Promise((resolve,reject)=>{resolveRequest=resolve;rejectRequest=reject;});},
    load:async()=>{throw new Error('Refresh failed');},
  });
  vm.runInContext(code,context);
  vm.runInContext("display([{id:1,status:'Applied'}])",context);
  const first=elements['confirm-status'].onclick();
  assert.equal(rendered[0].status,'Offer');
  assert.equal(button.disabled,true);
  await elements['confirm-status'].onclick();
  assert.equal(requests,1);
  // A concurrent list refresh must keep the optimistic badge and lock.
  vm.runInContext("display([{id:1,status:'Applied'}])",context);
  assert.equal(rendered[0].status,'Offer');
  rejectRequest(new Error('Save failed'));
  await first;
  assert.equal(rendered[0].status,'Applied');
  assert.equal(button.disabled,false);
  assert.equal(elements['request-error'].hidden,false);
  context.pendingStatusId='1';
  const second=elements['confirm-status'].onclick();
  resolveRequest({json:async()=>({id:1,status:'Offer'})});
  await assert.rejects(second,/Refresh failed/);
  assert.equal(rendered[0].status,'Offer');
  assert.equal(button.disabled,false);
});

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
