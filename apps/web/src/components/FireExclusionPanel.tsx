import { useEffect, useRef, useState } from "react";
import { request, staffHeaders } from "../api";

type Exclusion = {id:string;reason:string;active:boolean;edge_ids:string[];created_at:string};
const DEMO = JSON.stringify({type:"Polygon",coordinates:[[[78.078,30.380],[78.079,30.380],[78.079,30.381],[78.078,30.381],[78.078,30.380]]]},null,2);

export function FireExclusionPanel({credential,onRefresh}:{credential:string;onRefresh:()=>Promise<void>}) {
  const [items,setItems]=useState<Exclusion[]>([]), [geometry,setGeometry]=useState(DEMO);
  const [reason,setReason]=useState("Demonstration fire perimeter — operator exercise");
  const [available,setAvailable]=useState(false), [message,setMessage]=useState(""), [busy,setBusy]=useState(false);
  const idempotency=useRef<string | undefined>(undefined);
  async function load() {
    const [status,records]=await Promise.all([request<{status:string}>("/api/v1/spatial/status"),request<Exclusion[]>("/api/v1/fire-exclusions")]);
    setAvailable(status.status==='connected');setItems(records);
  }
  useEffect(()=>{let active=true;Promise.all([request<{status:string}>("/api/v1/spatial/status"),request<Exclusion[]>("/api/v1/fire-exclusions")]).then(([status,records])=>{if(active){setAvailable(status.status==='connected');setItems(records);}}).catch(e=>{if(active)setMessage(e.message);});return()=>{active=false;};},[]);
  async function publish() {
    setBusy(true);setMessage("");
    try {
      const polygon=JSON.parse(geometry);
      idempotency.current ??= crypto.randomUUID();
      await request("/api/v1/fire-exclusions",{method:"POST",headers:staffHeaders(credential),body:JSON.stringify({exclusion_id:idempotency.current,geometry:polygon,reason})});
      await load();await onRefresh();setMessage("Perimeter published. Intersecting routes were invalidated and their reservations released.");
    } catch(e){setMessage(e instanceof Error?e.message:'Perimeter publication failed.');}
    finally{setBusy(false);}
  }
  async function toggle(item:Exclusion) {
    setBusy(true);setMessage("");
    try {await request(`/api/v1/fire-exclusions/${item.id}`,{method:"PUT",headers:staffHeaders(credential),body:JSON.stringify({active:!item.active})});await load();await onRefresh();setMessage("Perimeter status updated. Previously invalidated bookings remain invalid.");}
    catch(e){setMessage(e instanceof Error?e.message:'Update failed.');}finally{setBusy(false);}
  }
  return <section className="ml-panel fire-exclusion-panel"><p className="eyebrow">POSTGIS / HARD SPATIAL CONSTRAINTS</p><h3>Fire-perimeter control</h3><p>Every road touching an active perimeter is excluded. Publishing a perimeter releases reservations on affected routes. Demonstration perimeters are operator exercises, not observed fires.</p>
    {!available&&<p role="status">Spatial perimeter service unavailable. New geometry cannot be published; saved exclusions remain enforced.</p>}
    {message&&<p role="status">{message}</p>}
    <details><summary>Import a perimeter geometry</summary><form onSubmit={e=>{e.preventDefault();void publish();}}><label className="form-label">Reason<input value={reason} minLength={3} maxLength={300} onChange={e=>{setReason(e.target.value);idempotency.current=undefined;}} required/></label><label className="form-label">GeoJSON Polygon<textarea value={geometry} maxLength={80000} rows={8} onChange={e=>{setGeometry(e.target.value);idempotency.current=undefined;}} required/></label><button className="primary-action" disabled={busy||!available||!credential}>Publish perimeter and invalidate affected routes</button></form></details>
    <div>{items.length?items.map(item=><article className="shelter-detail" key={item.id}><strong>{item.reason}</strong><p>{item.edge_ids.length} intersecting segments · {item.active?'active hard exclusion':'inactive'}</p><button className="secondary-action" disabled={busy||!credential} onClick={()=>{void toggle(item);}}>{item.active?'Deactivate perimeter':'Reactivate perimeter'}</button></article>):<p>No perimeters have been published.</p>}</div>
  </section>;
}
