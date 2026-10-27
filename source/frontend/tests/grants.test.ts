import assert from 'node:assert/strict';
import test from 'node:test';
import {parseGrantList, topGrants} from '../lib/grants.ts';

test('top match uses the highest visible personalized score and preserves input order',()=>{
 const rows=parseGrantList([{id:1,title:'Older',status:'active',ai_match_score:22},{id:2,title:'Best',status:'active',ai_match_score:49},{id:3,title:'Unknown',status:'active'}]);
 assert.equal(topGrants(rows)[0].id,2);
 assert.equal(rows[0].id,1);
});

test('zero alignment and historical/source warnings survive parsing',()=>{
 const [row]=parseGrantList([{id:1,title:'Historical',status:'active',ai_match_score:0,catalog_state:'historical_announcement',requirements_warning:'Unverified source'}]);
 assert.equal(row.ai_match_score,0);
 assert.equal(row.catalog_state,'historical_announcement');
 assert.equal(row.requirements_warning,'Unverified source');
});
