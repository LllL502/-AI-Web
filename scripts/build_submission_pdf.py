"""Build the source-backed <=30-page technical document and editable Markdown."""
from pathlib import Path
import os
from html import escape
import json
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, Flowable
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Polygon
from reportlab.lib.pagesizes import A4

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/pdf'
SRC=ROOT/'docs/submission'
OUT.mkdir(parents=True,exist_ok=True)
SRC.mkdir(parents=True,exist_ok=True)
pdfmetrics.registerFont(TTFont('CN',os.environ.get('CAMPUS_TRACE_CJK_FONT','C:/Windows/Fonts/msyh.ttc')))
pdfmetrics.registerFont(TTFont('CNBold',os.environ.get('CAMPUS_TRACE_CJK_BOLD_FONT','C:/Windows/Fonts/msyhbd.ttc')))
NAVY=colors.HexColor('#152942');BLUE=colors.HexColor('#2368EF');TEAL=colors.HexColor('#087F8C');GRAY=colors.HexColor('#586A81');LIGHT=colors.HexColor('#F1F6FD')
styles={
 'body':ParagraphStyle('body',fontName='CN',fontSize=11.1,leading=20.5,textColor=NAVY,spaceAfter=13,wordWrap='CJK'),
 'small':ParagraphStyle('small',fontName='CN',fontSize=8.4,leading=13,textColor=GRAY,spaceAfter=7,wordWrap='CJK'),
 'h2':ParagraphStyle('h2',fontName='CNBold',fontSize=14,leading=22,textColor=BLUE,spaceBefore=8,spaceAfter=9,wordWrap='CJK'),
 'cell':ParagraphStyle('cell',fontName='CN',fontSize=9.3,leading=15.5,textColor=NAVY,wordWrap='CJK'),
 'head':ParagraphStyle('head',fontName='CNBold',fontSize=9,leading=15,textColor=colors.white,wordWrap='CJK'),
}
def p(text,style='body'):
 text=text.replace('–','-').replace('—','-').replace('‑','-')
 return Paragraph(escape(text).replace('\n','<br/>'),styles[style])

class Screenshot(Flowable):
 def __init__(self,path):
  super().__init__();self.path=path;self.width=476;self.height=175
 def draw(self):
  from PIL import Image
  with Image.open(self.path) as im:w,h=im.size
  self.canv.saveState();clip=self.canv.beginPath();clip.rect(0,0,self.width,self.height);self.canv.clipPath(clip,stroke=0)
  height=h*self.width/w
  self.canv.drawImage(str(self.path),0,self.height-height,width=self.width,height=height)
  self.canv.restoreState()
def table(rows,widths=None):
 data=[[p(str(c),'head' if i==0 else 'cell') for c in row] for i,row in enumerate(rows)]
 t=Table(data,colWidths=widths or [476/len(rows[0])]*len(rows[0]),hAlign='LEFT')
 t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),9),('RIGHTPADDING',(0,0),(-1,-1),9),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),('ROWBACKGROUNDS',(0,1),(-1,-1),[LIGHT,colors.white]),('LINEBELOW',(0,0),(-1,-1),.4,colors.HexColor('#DCE5F0'))]))
 return t
def diagram(kind):
 d=Drawing(476,210)
 def box(x,y,w,h,lines,primary=False):
  d.add(Rect(x,y,w,h,rx=9,ry=9,fillColor=BLUE if primary else LIGHT,strokeColor=BLUE if primary else colors.HexColor('#C9DAF0')))
  for i,line in enumerate(lines):d.add(String(x+w/2,y+h/2+7*(len(lines)-1)-14*i,line,fontName='CNBold' if i==0 else 'CN',fontSize=9,textAnchor='middle',fillColor=colors.white if primary else NAVY))
 def arrow(x1,y1,x2,y2):
  d.add(Line(x1,y1,x2,y2,strokeColor=TEAL,strokeWidth=1.3))
  if x2>x1:points=[x2,y2,x2-6,y2+3,x2-6,y2-3]
  elif x2<x1:points=[x2,y2,x2+6,y2+3,x2+6,y2-3]
  elif y2>y1:points=[x2,y2,x2-3,y2-6,x2+3,y2-6]
  else:points=[x2,y2,x2-3,y2+6,x2+3,y2+6]
  d.add(Polygon(points,fillColor=TEAL,strokeColor=TEAL))
 if kind=='flow':
  labels=[['描述 / 照片','回忆外观与时间'],['小寻整理','原文证据与核对'],['检索与候选','当前校区公开记录'],['认领与实物交接','权限核验、双方确认']]
  for i,line in enumerate(labels):box(i*122,123,110,65,line,i==1)
  for i in range(3):arrow(i*122+110,156,(i+1)*122,156)
  box(123,15,230,60,['暂无线索时发布','完整确认后提交审核，不自动认定归属']);arrow(177,123,177,75)
 elif kind=='architecture':
  box(0,142,138,62,['Vue网站','小寻、表单、广场、管理端']);box(170,142,138,62,['Django REST API','权限 / 校区 / 协议 / 事务'],True);box(340,142,136,62,['MySQL 8.4','业务、向量、任务、审计'])
  arrow(138,173,170,173);arrow(308,173,340,173)
  box(0,10,145,70,['本地推理','Qwen视觉与对话','Qwen语义向量']);box(166,10,145,70,['排序与业务工具','证据门槛 / 幂等确认','授权动作与通知']);box(332,10,144,70,['本地童声','CPU预加载','共享GPU按需生成'])
  arrow(215,142,74,80);arrow(239,142,239,80);arrow(265,142,403,80)
 elif kind=='data':
  for x,lines in [(0,['学校 School','高校来源目录']),(166,['校区 Campus','当前请求数据范围']),(332,['地点 / 服务站','CampusLocation / Station'])]:box(x,145,144,60,lines)
  arrow(144,175,166,175);arrow(310,175,332,175)
  box(0,25,144,70,['物品 / 图片','Item / MediaAsset','审核与业务状态分开']);box(166,25,144,70,['认领 / 交接','Claim / Appointment','事件与双方确认']);box(332,25,144,70,['会话 / 通知 / 审计','Conversation / Notification','对象范围与事件去重'])
  arrow(405,145,72,95);arrow(144,60,166,60);arrow(310,60,332,60)
 elif kind=='agent':
  for x,y,lines,main in [(0,140,['用户自然表达','补充、否定、未知信息'],False),(166,140,['模型提出结构化结果','内容与原文片段'],True),(332,140,['服务端验证','字段、证据、日期与隐私'],False),(0,20,['实际结果回到对话','成功 / 待审核 / 被拒绝'],False),(166,20,['业务执行器','权限、状态、幂等、事务'],True),(332,20,['用户明确确认','完整确认句或确认按钮'],False)]:box(x,y,144,65,lines,main)
  arrow(144,172,166,172);arrow(310,172,332,172);arrow(404,140,404,85);arrow(332,52,310,52);arrow(166,52,144,52)
 return d

pages=[]
def page(title,section,paras,rows=None,diagram_kind=None):pages.append(dict(title=title,section=section,paras=paras,rows=rows,diagram=diagram_kind))
page('阅读导航与验收摘要','文档说明',[
 '本技术文档对应2026年11月17日的本地验收版本。项目名称为“寻迹”，团队为“森林冰火人”，成员冷绮文、段宇桐，学校为西安交通大学。文档覆盖项目、需求、架构、AI方案、核心实现、测试部署与总结，重点说明选型理由、集成方式、优化策略和创新边界。',
 '代码仓库：https://github.com/LllL502/-AI-Web。当前未提供已上线的正式域名，不把本地演示、测试脚本或部署模板写成服务器已完成验收。本文不包含视频内容。',
 '验证数字来自留存的测试与评测证据：后端完整回归233项、前端74项通过；80个页面与视口组合无运行异常或非预期请求失败。真实对话与非缓存童声另行验证，不能用模拟接口替代模型效果验证。'],[
 ['章节','阅读目标','页码'],['1 项目概述','价值、产品边界','3'],['2 需求分析','角色、场景与完整流程','4–5'],['3 系统架构','分层、数据关系、权限','6–8'],['4 AI技术方案','选型、集成、检索与优化','9–13'],['5 核心功能实现','发布认领、通知与参数','14–15'],['6 测试与部署','回归、固定评测、复现部署','16–18'],['7 总结与展望','技术及应用创新、局限','19'],['证据与复现索引','源码、依赖、材料位置','20']])
page('1 项目概述：从模糊回忆到可核对线索','项目概述',[
 '校园失物招领往往依赖群聊关键词和分散表单。失主常只记得蓝色笔袋或昨天使用过等零散线索，拾得者又可能采用另一种描述。检索困难之外，还存在校区混淆、证件信息过度公开，以及认领后实物交接缺少确认的问题。',
 '寻迹把小寻作为统一交互入口：接收一句描述或一张照片，整理已知事实，允许用户说明“不知道”“记不清”，再到当前校区仍公开、开放的数据库记录中寻找候选。候选不是模型编造的物品，图片、时间、地点和评分依据供用户逐一核对。',
 '产品同时保留普通表单、广场、地图与服务站。AI不可用时，用户仍可按字段发布或浏览；当存在匹配候选时，再通过私密核验证据、人工审核和实物交接完成闭环。',
 '面向用户的价值是减少反复填写、降低描述不一致导致的漏检；面向协调员的价值是明确待办、权限和审核轨迹。当前系统验证的是工程链路与固定案例，不以演示数据证明真实校园的找回率。',
 '演示学校与演示校区承担流程展示。真实校区不批量填入虚构招领记录；演示参考照片与现场实拍、合成插图明确区分。'])
page('2 需求分析：角色、任务与约束','需求分析',[
 '核心任务不是“给出一个看起来像答案的回复”，而是让信息提取、检索、确认和实际办理在同一授权边界内完成。每个角色只能在相应对象与校区范围内操作。',
 '输入完整性不等于强迫用户猜测。已知日期、未知钟点应分开保存；“昨天或前天”不应转换成一个确定日期。用户可以排除候选、纠正特征，或者选择先发布启事。',
 '非功能约束包括：可见图片与业务记录权限一致；私密证据不进入公开检索语料；AI任务可超时和取消；写操作幂等；配置版本可追溯；通知与业务事务共同提交。'],[
 ['角色','主要任务','权限边界'],['游客','浏览公开广场与校园信息','只见审核通过且OPEN记录'],['普通用户','发布、检索、收藏、申请、沟通、交接','本人记录或明确授权对象'],['拾得者','核对认领证明、选择交接方式','本人招领相关流程'],['站点协调员','站点审核、保管、交接','有效站点成员与具体能力'],['管理员','字典、内容、参数和运营管理','服务器角色校验，业务查询按校区']])
page('2.1 端到端用户流程','需求分析',[
 '寻找流程：用户说明遗失情况，小寻提取可确认字段并按需要追问；图片先形成可见外观描述，用户核对后再参与检索。候选只有实际数据库引用，用户可以展开、排除或继续补充。',
 '招领流程：用户表达“捡到”后保持FOUND类型，整理标题、外观、地点与时间，最后核对发布草稿。没有用户实拍照片时不自动生成虚构照片。',
 '认领流程：用户选中候选后关联自己的遗失记录，通过私密通道提交独有核验特征。拾得者或有权人员核验，之后选择直接交接或服务站交接；完成状态由应有双方的确认推动。',
 '“先不要提交认领”“我还没收到物品”等否定、提问、引用与条件句不能形成写操作同意。用户界面保留清晰确认按钮，语言确认只接受完整独立的确认语句。'],diagram_kind='flow')
page('3 系统架构：界面、推理与业务分层','架构设计',[
 '前端使用Vue 3、TypeScript与Pinia；Three.js呈现小寻全身形象和动作，ECharts用于解释或运营展示。前端负责交互与草稿展示，不承担最终权限判断。',
 'Django REST API统一处理会话认证、CSRF、当前校区、字段协议、对象归属、角色能力及状态机。MySQL保存业务记录、向量、任务、通知和审计；文件存储单独补偿，不能假设数据库回滚会删除文件。',
 '模型通过适配层提供对话/视觉、向量和童声。生成式结果先校验再进入应用；实际写动作进入既有业务服务，不允许模型直接写数据库。独立服务就绪检查不试生成、不争抢GPU。'],diagram_kind='architecture')
page('3.1 数据关系与版本设计','架构设计',[
 'School—Campus—CampusLocation构成校园范围，Station归属地点；Item通过location关联校区。审核状态与业务状态分开，公开资格统一为审核通过且OPEN。MediaAsset的原图、缩略图与所属记录一起检查可见性。',
 'Claim关联招领物品、申请人和相关遗失信息；ClaimEvent保留状态变化，预约、保管与归还记录描述交接。Conversation保存校区及参与关系；Notification带校区和唯一事件键。',
 'ItemVector以公开文本内容哈希和模型身份维护；AlgorithmConfig发布或被引用后冻结。新参数通过复制新版本形成草稿；唯一活动槽位与数据库约束确保只有一个活动配置，历史内容不被原地改写。'],diagram_kind='data')
page('3.2 安全、隐私与一致性','架构设计',[
 '认证与范围：使用服务端会话和CSRF保护写请求；角色并不替代对象归属与站点能力检查。校区选择只确定数据范围，不授予管理权限。消息列表、详情及发送复用同一参与人与校区范围。',
 '公开数据最小化：检索只使用公开字段；姓名、学号、电话、密码、序列号及私密核验证据不应进入公开描述。图片观察要求不转录证件信息，用户核对后才应用。通知预览不复制证明、审核私密说明或消息正文。',
 '媒体授权：生产代理不直接公开整个媒体目录。原图和缩略图经过后端检查；待审核、关闭等非公开状态按本人、管理员、相关服务站或认领授权决定，响应禁止缓存。收藏读取也重新检查资格，避免从摘要绕过详情权限。',
 '事务与文件：数据库中的业务、审计和通知一起提交/回滚；文件写入登记到补偿上下文，覆盖图片保存、响应与最后提交失败。对账工具默认只报告，明确执行清理时保留引用文件及宽限期内文件。',
 '写操作需要确认及幂等键，重试同一操作不重复创建；关联认领历史的物品不能直接删除，界面给出保留说明。该边界保护可追溯交接记录。'])
page('4 AI选型：能力与本机约束匹配','AI技术方案',[
 '选型考虑中文对话、物品外观理解、可部署性和单卡8GB显存预算。模型能力与业务可靠性分开：选择中文模型不能替代严格协议、输入证据和实际业务检查。',
 '本次采用预训练模型推理，不声称团队训练了这些模型。模型权重不放入代码仓库，下载版本和许可由相应模型卡约束。首次下载需网络，下载后本地推理可离线工作。',
 '本机配置不是云服务器配置。云端部署必须提供上线后持续运行的推理服务；网站上线不能依赖开发电脑开机。当前Compose模板不自动包含GPU推理服务，需在服务器环境完成部署与推理验收。'],[
 ['能力','选型','理由与边界'],['对话/外观理解','Qwen3-VL 4B Instruct','同一模型处理中文结构化与图片；外观细节可能误判'],['语义向量','Qwen3-Embedding 0.6B','独立向量模型，支持中文改写；相似不等于归属'],['自然童声','Qwen3-TTS 1.7B VoiceDesign','合成角色语调；CPU预加载、GPU按需生成'],['接口运行时','Ollama / 本地HTTP','统一适配；服务配置存在不等于实际就绪']])
page('4.1 小寻：受约束的对话与业务工具','AI集成',[
 '连续对话维护用户与校区绑定、限时签名的记忆，记录来源、草稿、候选和已明确未知的字段。模型选择意图并提供结构化字段与原文片段；服务端拒绝未声明字段、无证据值及不符合协议的结构。',
 '公示文案由经过核对的字段组合，不能把“对”“不是”“补充”等聊天文本直接拼成标题。日期与钟点分别解析，相对日期绑定到原发言参考日；跨午夜继续对话不重新漂移。',
 '只读检索、候选展开与写工具明确区分。执行器重新获取当前有效对象，再检查确认、所有权、校区、状态和幂等。模型回复“已完成”不能代替接口真实结果；失败必须显示实际结果并允许普通流程继续。'],diagram_kind='agent')
page('4.2 图片理解与用户实拍处理','AI集成',[
 '图片理解入口验证真实JPEG/PNG/WebP内容，限制8MB和2000万像素，纠正EXIF方向、转RGB并缩放后才发送模型。提示仅描述可见类别、颜色、形状、材质和外观，不猜测主人、地点或事件时间，不转录个人号码。',
 '图片观察先显示为待核对描述。用户确认后把可见特征并入文字来源，再生成结构化草稿；模型观察不会自动创建发布记录，也不会替用户确定隐蔽特征。',
 '发布图片是另一条受控链路：最多3张，单张5MB，解码后重编码并去除元信息，生成缩略图，利用内容摘要检查重复。图片数据库记录与磁盘文件的一致性通过事务补偿和孤立文件对账维护。',
 '两条链路的限制不同，因为图片理解只是临时推理输入，发布照片是持久业务附件。技术表达必须区分“图片转文字后检索”与“图文同空间直接检索”，本项目当前实现的是前者。',
 '演示照片的来源作者与页面记录在素材清单中；同类参考与合成图分别标注。用户没有照片时显示暂无实拍，不用生成图制造确定感。'])
page('4.3 语义召回与可解释六因子','检索方案',[
 '候选资格先于向量相似度：按当前校区、相反信息类型、审核通过和OPEN状态筛选，再读取公开文本。文本由类别、品牌、颜色、标题和描述组成，向量按模型身份与内容哈希持久化，避免每次重复编码全部物品。',
 '相似度使用向量余弦：cos(q,c) = (q·c) / (||q|| × ||c||)。语义召回解决措辞不一致；随后结合类别、地点、时间、颜色和品牌重排。默认权重分别为文本0.50、类别0.15、地点0.12、时间0.10、颜色0.08、品牌0.05。',
 '设a_i表示该因子是否可用：coverage = Σ(w_i × a_i)；有效权重 = w_i × a_i / coverage；基础分 = Σ(有效权重 × 因子分)。缺失字段不当成冲突，也不强行按0分加入总分。',
 '当前语义重排对明确冲突另乘工程惩罚：类别0.25、颜色0.55、品牌0.65、时间0.35。展示门槛evidence_gate_v1要求最终分至少0.6，且无明确类别或时间冲突；先过滤完整召回池，再取展示数量。',
 '界面提供缺失因子、冲突、有效权重及版本信息。排序分与门槛是工程规则，不是所有权概率，也未证明全局最优。普通TF-IDF基线保留用于可解释对照，不把两条文本相似度路径混称为同一模型。'])
page('4.4 稳定性、资源与童声优化','优化策略',[
 '数据库准入锁限制全局并发，当前显卡配置维持1。每次AI请求有用户与校区范围、操作指纹、幂等键、任务租约和总预算；取消不是只停止动画，而是协作检查服务端预算和任务状态。',
 '模型与内容哈希控制向量增量更新，索引写入前重新核对当前公开资格及内容，防止编辑期间把旧向量写回。首次部署、内容或模型修订后预建/维护索引；未配置时的关键词路径明确标为降级。',
 '小寻形象由Three.js呈现完整身体，动作约20秒轮换、气泡低频出现；不可见区域和降低动态效果设置会减少无效渲染。形象交互与语音计算分开，等待或取消语音不阻塞用户继续输入。',
 '童声先在CPU预加载权重，加载完成才报告就绪；实际生成前确认服务可用，再释放闲置Ollama显存并按需使用GPU，完成后回到CPU。准备中的服务不能仅因文件存在就报告“可用”。',
 '真实验证中曾发现冷请求超时，随后补充预加载与实际状态检查。最终动态句通过网站接口约6.94秒生成2.4秒、24kHz音频。这只是该次本机样例，不是多人并发或平均延迟承诺。'])
page('5 核心实现：发布、核验与实物交接','核心功能',[
 '发布：用户核对标题、物品特征、地点、日期和时间后提交；服务器执行内容审核，并保存提交版本与审计。常规表单和小寻调用相同业务服务。已知日期不等于虚构具体钟点，缺少必要信息时需要用户继续核对。',
 '状态分离：物品审核状态管理草稿、待审、通过或驳回；业务状态管理寻找中、认领保留、归还、关闭或过期。广场、地图、检索与图片访问不能各自采用不同的“公开”定义。',
 '认领：申请关联实际招领物品与本人遗失记录；核验证据私密保存，由拾得者或授权人员审核。通过、驳回、补充材料等状态变化有事件记录，不凭模型相似度直接通过。',
 '交接：直接交接记录双方各自确认；服务站交接包含预约、保管与授权核验。不能替另一方确认实物，不会因为一句普通聊天或一个高分就结束整个找回流程。',
 '删除：没有关联流程时按本人权限和状态处理；有关联认领的记录必须保留，关闭可从广场下架但不抹掉交接历史。异常响应整理成可读原因，不能给用户显示空对象。'])
page('5.1 通知、消息与参数中心','核心功能',[
 '订阅：当前校区的新公开线索按信息类型、类别、地点与关键词过滤。关键词匹配度是查询词在公开文本中的命中比例，界面明确标名，不冒充语义概率。同一订阅对同一物品最多提醒一次，暂停与最低匹配度在事件发生时生效。',
 '通知：发布审核、认领状态和站内消息生成站内提醒，遵循用户偏好、校区和事件去重。业务与通知共同提交/回滚，不在数据库事务中请求外部消息服务或大模型。预览仅提示进度或有新消息，不复制私密内容。',
 '消息：列表、详情与发送统一参与人和校区范围；独立会话显式归属校区。输入检查真实字符串、非空白和4000字上限，拒绝用自动字符串转换接受对象、列表或数字。',
 '参数中心：管理员可从已有版本复制新草稿，编辑权重、阈值、词典和别名，保存后再发布。已发布或被引用的配置不可改写；状态区分当前活动、历史已发布、已引用和未发布草稿，重新启用历史版本也有明确操作。',
 '系统管理分别展示小寻对话、语义检索、图片理解和童声状态；基础网站存活与AI就绪分开。健康检查只探测服务与模型注册，不通过试生成占用显卡。'])
page('6 测试策略与本地验收','测试与验证',[
 '测试分为纯逻辑/组件、MySQL接口与事务、浏览器交互、真实模型样例和备份恢复。模拟接口用来验证界面协议与错误处理；真实推理另行检查，二者不能相互代替。',
 '专项反例包含否定、问题、引用和条件句不能触发写操作；私有收藏摘要不能泄露；普通上传最终提交失败必须清理文件；忘记钟点不抹掉日期；消息与地图范围一致；通知暂停、去重和回滚有效。',
 '233项完整后端结果之后，隐藏收藏取消的兼容分支又通过相关16项专项验证。所有数字对应留存版本与范围，不能据此保证没有其他边界缺陷。'],[
 ['验证类别','结果','说明'],['后端完整回归','233项通过','MySQL；104.59秒'],['最终相关专项','16项通过','隐藏收藏、语音及十项反例'],['前端组件/逻辑','74项通过 / 19文件','包括确认安全、配置与状态'],['正式构建','通过','TypeScript检查与Vite构建'],['页面与视口','80个组合','游客/学生/管理员；桌面/手机'],['参数交互浏览器','2项通过','复制、编辑、发布；写接口模拟'],['真实对话与童声','分别通过','连续日期保留；非缓存语音']])
page('6.1 固定评测与效果边界','测试与验证',[
 '固定数据集assistant-fixed-v2有24条查询，开发和验证各12条，分别包含8条正例与4条无答案。参赛者已认可构造场景及标签；该认可不等于真实用户数据或第三方盲测。',
 '对比从已确认字段开始，比较关键词、纯语义、语义六因子和加候选过滤四条路径，使用实际Qwen3-Embedding 0.6B。图像理解和LLM提取准确率不在这组检索评测范围内。',
 '候选过滤在这组案例中减少了无答案时强行返回的情况；门槛是在开发案例检查后设定，验证场景已公开且继承先前设计，不能称为独立盲测。提高门槛也可能漏掉真实但描述模糊的失物，仍需困难样本与授权真实数据评估。'],[
 ['方法','开发首位命中','验证首位命中','无答案误返（开发/验证）'],['关键词','0/8','4/8','4/4；3/4'],['纯语义','8/8','8/8','4/4；4/4'],['语义六因子','8/8','8/8','4/4；4/4'],['六因子+候选过滤','8/8','8/8','0/4；0/4']])
page('6.2 安装、部署与运行保障','测试与部署',[
 '复现采用Python 3.12、MySQL 8.4与锁定的前端依赖。Windows完整演示通过setup、start、health、stop入口；普通开发环境也可按依赖清单创建虚拟环境、迁移、导入种子并分别启动Django和Vite。模板模拟模式必须明确标识。',
 '环境变量分为网站与数据库、地图、本地对话/视觉/向量、资源预算及生产HTTPS。真实.env、密钥、模型文件、运行数据库、用户上传和日志不进入仓库。模型首次下载与依赖安装需要网络，不把权重打进Git。',
 '生产方案为固定域名→Caddy HTTPS→Vue静态页面与Django/Waitress→MySQL。数据库不开放公网端口，媒体经后端授权；随机密钥、Cookie安全属性与HTTPS在生产环境单独配置。',
 'GPU推理服务需上线后持续运行。当前Compose模板并不自动启动Ollama或童声；视觉/向量适配器限制回环HTTP，需要明确后端与推理服务的部署网络，不能把开发电脑地址当成云端服务。',
 '备份先检查数据库导出成功，再压缩、验证媒体和SHA256，全部通过后才发布完整备份目录并清理旧备份。恢复在隔离临时库演练，不覆盖业务库。本地已有52张表、8611条记录数量及421个媒体文件内容一致的恢复证据；正式服务器仍需重新验收。'])
page('7 创新点、局限与后续计划','总结与展望',[
 '技术创新侧重工程组合：将自然表达、原文证据、签名对话记忆、可解释多因子与受限工具结合。模型提出草稿，应用验证和执行；缺失信息与冲突分开，检索允许拒绝返回，而不是每次凑满候选。',
 '应用创新侧重完整闭环：小寻既帮助失主寻找，也帮助拾得者整理招领；从同一聊天入口衔接核验、预约、消息和实物确认。可爱形象降低使用门槛，真正结果仍由业务接口反馈，避免把角色动画当作智能体能力本身。',
 '安全与可复现创新：校区、公开资格和附件权限贯穿多个入口；配置冻结及单一活动版本保护结果复现；通知与业务共事务，磁盘写入额外补偿；真实推理、模拟测试与合成评测分别留证。',
 '当前局限：小样本评测偏乐观；图像细节可能误判；单卡并发为1；图片仍经描述桥接，不支持共享空间图文相似检索；未完成正式服务器或多人容量验收。未宣称这些工程组合构成原创基础模型或算法首创。',
 '后续优先级：完成固定域名及服务器验收；采集授权自然描述、同款物品与困难负例；测试拒绝规则的漏检；按真实容量考虑异步队列与独立语音资源。扩展时保留现有隐私边界、人工确认与版本证据。'])
page('证据、源码与复现索引','材料索引',[
 '仓库提供后端、前端、迁移、测试、环境模板及精选证据；模型和运行数据另行安装。完整的环境步骤、演示账号边界、素材来源与提交状态在对应文档中。',
 '原始本地Git及新建远程仓库在归档前均没有提交，因此不存在可导入的早期Git历史。本次从真实整理开始记录，未补造作者、时间或开发提交；阶段记录可以作为过程资料，但不是原始Git历史的替代品。',
 '本技术文档未填入未提供的正式域名、指导教师、参赛编号或个人分工。团队和成员姓名已由项目负责人提供。服务器验收完成后，应更新上线地址和对应证据，不改变本次本地结果的时间与范围。'],[
 ['材料','仓库位置'],['项目、技术与团队','README.md'],['环境、模型与依赖','docs/submission/环境与复现.md；backend/.env*.example；各锁文件'],['当前修复与验收','docs/49_前后端十项修复与验收.md；evidence/verification-summary.json'],['固定检索数据及复核','data/benchmark/assistant-fixed-v2*.json'],['原始评测报告','evidence/benchmark/assistant-fixed-v2-all-20261115T144313957097.json'],['模型与排序实现','backend/apps/assistant/；backend/apps/matching/'],['素材来源与边界','THIRD_PARTY_NOTICES.md；data/demo-photos/sources.json'],['部署与备份','deploy/；docker-compose.prod.yml；docs/13_正式生产部署.md'],['正式托管入口','https://github.com/LllL502/-AI-Web']])

TOTAL=len(pages)+1
def decoration(canvas,doc):
 canvas.saveState()
 canvas.setStrokeColor(colors.HexColor('#DFE7F2'));canvas.line(59,792,536,792)
 canvas.setFont('CN',8);canvas.setFillColor(GRAY);canvas.drawString(59,804,'森林冰火人  /  寻迹技术文档')
 canvas.drawRightString(536,804,'2026.11 · 本地验收版')
 canvas.drawString(59,31,'西安交通大学 · 冷绮文 / 段宇桐');canvas.drawRightString(536,31,f'{doc.page:02d} / {TOTAL:02d}')
 canvas.restoreState()
story=[]
cover=ParagraphStyle('cover',fontName='CNBold',fontSize=44,leading=58,textColor=NAVY,spaceAfter=20)
story.extend([Spacer(1,90),Paragraph('寻迹',cover),Paragraph('校园多模态智能寻物助手',ParagraphStyle('subtitle',fontName='CNBold',fontSize=21,leading=34,textColor=BLUE)),Spacer(1,24),p('技术文档','h2'),p('从模糊回忆，到可核对的线索。'),Spacer(1,55)])
story.append(table([['团队','森林冰火人'],['学校','西安交通大学'],['成员','冷绮文、段宇桐'],['参赛项目','第九届传智杯 AI WEB 网页开发挑战赛'],['文档版本','2026-11-17 · 本地验收材料']],widths=[92,384]))
story.extend([Spacer(1,32),p('多模态输入  ·  受限业务工具  ·  可解释检索  ·  安全交接','small'),PageBreak()])
md=['# 寻迹 · 校园多模态智能寻物助手技术文档','森林冰火人｜西安交通大学｜冷绮文、段宇桐｜2026-11-17','']
for i,section in enumerate(pages):
 flows=[p(section['section'],'small'),Paragraph(escape(section['title']),ParagraphStyle('title'+str(i),fontName='CNBold',fontSize=22,leading=33,textColor=NAVY,spaceAfter=21))]
 # Diagrams follow the first short introduction rather than crowding the heading.
 for j,text in enumerate(section['paras']):
  flows.append(p(text))
  if i==1 and j==0:
   screenshot=SRC/'images/home.png'
   if screenshot.is_file():flows.extend([Screenshot(screenshot),Spacer(1,6),p('图1  本地网站首页局部；演示校区信息不代表真实校园运营。','small')])
  if section['diagram'] and j==0:flows.extend([diagram(section['diagram']),Spacer(1,12)])
 if section['rows']:
  widths=[74,256,146] if i==0 else None
  if i==19:widths=[130,346]
  flows.append(table(section['rows'],widths))
 story.append(KeepTogether(flows))
 if i<len(pages)-1:story.append(PageBreak())
 md.extend(['## '+section['title'],'',*section['paras'],''])
 if section['rows']:
  rows=section['rows'];md.append('| '+' | '.join(rows[0])+' |');md.append('| '+' | '.join(['---']*len(rows[0]))+' |')
  md.extend('| '+' | '.join(row)+' |' for row in rows[1:]);md.append('')
 if section['diagram']:md.append('（对应PDF含矢量架构或流程图，生成脚本保留绘图源。）\n')
doc=SimpleDocTemplate(str(OUT/'寻迹_技术文档.pdf'),pagesize=A4,leftMargin=59,rightMargin=60,topMargin=66,bottomMargin=57,title='寻迹：校园多模态智能寻物助手技术文档',author='森林冰火人 · 冷绮文、段宇桐',subject='第九届传智杯AI WEB项目技术文档')
doc.build(story,onFirstPage=decoration,onLaterPages=decoration)
(SRC/'技术文档.md').write_text('\n'.join(md),encoding='utf-8')
(SRC/'technical-sections.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2),encoding='utf-8')
import shutil
shutil.copy2(OUT/'寻迹_技术文档.pdf',SRC/'寻迹_技术文档.pdf')
from pypdf import PdfReader
reader=PdfReader(OUT/'寻迹_技术文档.pdf')
assert len(reader.pages)==TOTAL and TOTAL<=30,(len(reader.pages),TOTAL)
text='\n'.join(page.extract_text() for page in reader.pages)
for keyword in ['冷绮文','段宇桐','需求分析','系统架构','选型','集成','优化','创新','233','74']:
 assert keyword in text,keyword
assert '段雨桐' not in text
(OUT/'技术文档核验.json').write_text(json.dumps({'pages':len(reader.pages),'max_pages':30,'team':'森林冰火人','members':['冷绮文','段宇桐'],'text_checks':'passed','render_checks':'pending'},ensure_ascii=False,indent=2),encoding='utf-8')
print(f'PDF generated: {TOTAL} pages')
