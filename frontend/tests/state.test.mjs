import test from 'node:test';
import assert from 'node:assert/strict';
import { upsert, applyMessage } from '../src/state.mjs';
test('stream data is deduplicated and memory bounded', () => {
  const old = [{id:'1',value:1},{id:'2',value:2}];
  assert.deepEqual(upsert(old,{id:'1',value:3},2),[{id:'1',value:3},{id:'2',value:2}]);
  assert.equal(upsert(old,{id:'3'},2).length,2);
});
test('alert acknowledgement replaces prior alert', () => {
  const state={alerts:[{id:'x',acknowledged:false}]};
  assert.equal(applyMessage(state,{type:'alert',data:{id:'x',acknowledged:true}}).alerts[0].acknowledged,true);
});
test('older REST snapshots cannot replace newer stream state',()=>{
 const state={sequence:10,events:[{id:'latest'}]};
 assert.equal(applyMessage(state,{type:'snapshot',sequence:8,data:{sequence:8,events:[]}}),state);
 const next=applyMessage(state,{type:'tdo',sequence:11,data:{id:'new'}});
 assert.equal(next.sequence,11);
});

test('acknowledgement preserves chronology', () => {
 const state={alerts:[{id:'new',acknowledged:false},{id:'old',acknowledged:false}]};
 const next=applyMessage(state,{type:'alert',data:{id:'old',acknowledged:true}});
 assert.deepEqual(next.alerts.map(x=>x.id),['new','old']);
 assert.equal(next.alerts[1].acknowledged,true);
});
