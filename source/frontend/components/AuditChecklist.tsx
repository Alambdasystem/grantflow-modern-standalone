"use client";
export type ChecklistItem={label:string;done:boolean;evidence:string;owner:string};
export default function AuditChecklist({items,onChange}:{items:ChecklistItem[];onChange:(items:ChecklistItem[])=>void}) {
 const update=(i:number,field:keyof ChecklistItem,value:string|boolean)=>onChange(items.map((item,n)=>n===i?{...item,[field]:value}:item));
 return <fieldset className="border rounded border-zinc-700 p-3 space-y-4"><legend>Audit checklist</legend>
 {items.map((item,i)=><div key={i} className="space-y-2 border-b border-zinc-700 pb-3">
 <label className="block">Check {i+1}<input required className="block w-full bg-zinc-900 p-2" value={item.label} onChange={e=>update(i,'label',e.target.value)}/></label>
 <label className="block">Evidence<textarea required={item.done} className="block w-full bg-zinc-900 p-2" value={item.evidence} onChange={e=>update(i,'evidence',e.target.value)}/></label>
 <label className="block">Responsible owner<input required={item.done} className="block w-full bg-zinc-900 p-2" value={item.owner} onChange={e=>update(i,'owner',e.target.value)}/></label>
 <label><input type="checkbox" checked={item.done} onChange={e=>update(i,'done',e.target.checked)}/> Complete with evidence</label>
 <button type="button" className="ml-4 underline" onClick={()=>onChange(items.filter((_,n)=>n!==i))}>Remove check {i+1}</button>
 </div>)}
 <button type="button" disabled={items.length>=100} className="underline" onClick={()=>onChange([...items,{label:'',evidence:'',owner:'',done:false}])}>Add checklist item</button>
 <p className="text-xs text-zinc-400">Save the revision to record these checks, evidence and owner in the audit history.</p>
 </fieldset>;
}
