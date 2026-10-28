import test from 'node:test';
import assert from 'node:assert/strict';
import {applicationError, requestedAmountError} from '../lib/form-feedback';
import {refreshApplicationViews} from '../lib/application-cache';

test('requested amount preserves optional blank and zero, rejects negative/nonfinite input',()=>{
  for(const value of ['', '0', '100.25']) assert.equal(requestedAmountError(value),undefined);
  for(const value of ['-1', 'NaN', 'Infinity', '1e999']) assert.ok(requestedAmountError(value));
});

test('API validation locations become inline amount and grant errors without losing the form',()=>{
  const result=applicationError({response:{data:{detail:[
    {loc:['body','amount_requested'],msg:'Input should be greater than or equal to 0'},
    {loc:['body','grant_id'],msg:'Select a valid grant'}
  ]}}});
  assert.match(result.fields.amount_requested,/greater/);
  assert.match(result.fields.grant_id,/valid grant/);
  assert.match(result.message,/highlighted/);
  assert.equal(applicationError({response:{data:{detail:'Reviewer approval is required'}}}).message,'Reviewer approval is required');
  assert.match(applicationError({}).message,/entries are retained/);
});

test('status and review changes refresh all affected application views',async()=>{
  const keys:unknown[]=[];
  const client={invalidateQueries:async({queryKey}:{queryKey:unknown[]})=>{keys.push(queryKey);}};
  await refreshApplicationViews(client as Parameters<typeof refreshApplicationViews>[0],42);
  for(const key of [['applications'],['dashboard-stats'],['grant-pipeline'],['renewals'],['application',42],['workflow',42],['application-readiness',42],['reviews',42]]) {
    assert.ok(keys.some(k=>JSON.stringify(k)===JSON.stringify(key)),JSON.stringify(key));
  }
});
