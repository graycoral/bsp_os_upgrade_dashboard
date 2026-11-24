import {createContext,useContext,useState} from 'react';
import {getDefaultGuiTestHost,type GuiTestHost} from './host';

export const GuiTestHostContext=createContext<GuiTestHost|undefined>(undefined);
export function useGuiTestHost(explicit?:GuiTestHost):GuiTestHost {
  const inherited=useContext(GuiTestHostContext);
  const [host]=useState(()=>explicit||inherited||getDefaultGuiTestHost());
  return host;
}
