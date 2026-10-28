import test from 'node:test';
import assert from 'node:assert/strict';
import {isHondaOnboarding,hondaBudget,hondaFiles,hondaSources} from '../lib/honda-onboarding';

test('Honda presentation requires the exact saved application, owner organization and grant marker',()=>{
 const app={id:47,organization_id:1,grant_id:72,form_data:{honda_2027_onboarding:{}}};
 assert.ok(isHondaOnboarding(app));
 for(const other of [{...app,id:48},{...app,organization_id:2},{...app,grant_id:1},{...app,form_data:{}}]) assert.equal(isHondaOnboarding(other),false);
});

test('proposed budget reconciles without inferring committed funding or missing balances',()=>{
 assert.deepEqual(hondaBudget(100000,425000,325000),{request:100000,total:425000,remaining:325000,reconciled:true});
 assert.equal(hondaBudget(90000,425000,325000).reconciled,false);
 assert.deepEqual(hondaBudget(undefined,425000,undefined),{request:null,total:425000,remaining:null,reconciled:false});
 assert.equal(hondaBudget(-1,425000,Infinity).reconciled,false);
});

test('Honda source inventory and verified portal remain separate from Grants.gov',()=>{
 assert.equal(hondaFiles.length,4);
 assert.equal(new Set(hondaFiles).size,4);
 assert.equal(hondaSources.portal,'https://www.cybergrants.com/hondacsr/quiz/');
 assert.ok(Object.values(hondaSources).every(url=>url.startsWith('https:')&&!url.includes('grants.gov')));
});
