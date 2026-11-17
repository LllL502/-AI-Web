// Short spoken turns keep the companion conversational and avoid reading cards.
export function xunSpokenText(content: string): string {
  const clean=content.replace(/https?:\/\/\S+/g,'').replace(/[*#_`]/g,'').trim()
  const sentences=clean.match(/[^。！？!?]+[。！？!?]?/g)??[]
  let result=''
  for(const sentence of sentences){if((result+sentence).length>80)break;result+=sentence;if(result.length>=35)break}
  return result || clean.slice(0,76)+'。'
}
