export function Bar({value,label}:{value:{percent?:number|null};label:string}) {
 const percent=typeof value.percent==='number'&&Number.isFinite(value.percent)&&value.percent>=0&&value.percent<=100?value.percent:null;
 if(percent==null)return <div className="bar bar-na" role="status" aria-label={`${label}: 해당 없음`}><span className="audit-sr-only">해당 없음</span></div>;
 return <div className="bar" role="progressbar" aria-label={label} aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}><i style={{transform:`scaleX(${percent/100})`}}/></div>;
}
