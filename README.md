

\# OpsDesk Agent



基于 LangGraph、Qwen3、RAG 和 FastAPI 构建的本地企业 IT 智能服务 Agent。



\## 1. 项目介绍



OpsDesk Agent 是一个面向企业 IT 服务场景的 AI Agent 演示项目。



系统支持：



\- 企业 IT 知识库问答

\- 本地大模型语义理解

\- RAG 检索增强生成与文档来源展示

\- 基于 Tool Calling 的结构化工单规划

\- LangGraph 工作流编排

\- Human-in-the-loop 人工审批

\- SQLite 工单持久化

\- 工作流检查点恢复

\- 工单创建幂等性保护

\- FastAPI 接口服务

\- Streamlit 可视化界面



项目使用本地 Ollama 运行模型，演示数据不代表真实企业制度。



\## 2. 核心技术栈



| 技术 | 作用 |

|---|---|

| Python | 主要开发语言 |

| LangGraph | Agent 工作流与状态管理 |

| LangChain / ChatOllama | 本地模型调用 |

| Qwen3:8b | 回答生成与工单规划 |

| BGE-M3 | 文本向量化 |

| Chroma | 向量存储与检索 |

| SQLite | 工单及检查点持久化 |

| FastAPI | HTTP API |

| Streamlit | 可视化交互界面 |

| Ollama | 本地模型服务 |



\## 3. 系统架构



整体采用前端、API、Agent 工作流和数据存储分层设计。



```text

用户

&#x20;|

&#x20;v

Streamlit 前端

&#x20;|

&#x20;v

FastAPI

&#x20;|

&#x20;+---------------------------+

&#x20;|                           |

&#x20;v                           v

知识问答接口               工单管理接口

&#x20;|                           |

&#x20;v                           v

RAG 检索流程               LangGraph

&#x20;|                           |

&#x20;v                           v

BGE-M3 + Chroma            工单规划

&#x20;|                           |

&#x20;v                           v

Qwen3 回答生成             人工审批

&#x20;                            |

&#x20;                  +---------+---------+

&#x20;                  |                   |

&#x20;                  v                   v

&#x20;                 批准                拒绝

&#x20;                  |                   |

&#x20;                  v                   v

&#x20;             SQLite 写入           结束流程

```



LangGraph 的工作流状态可以通过 SQLite Checkpointer 保存，以支持审批中断与恢复。



\## 4. 功能介绍



\### 4.1 企业知识问答



用户输入 IT 问题，例如：



> 公司 VPN 无法连接，身份验证失败怎么办？



系统通过 BGE-M3 将问题向量化，在 Chroma 中检索相关知识片段，再由 Qwen3 生成回答。



回答包含可追溯的文档引用编号。



对于知识库范围外的问题，系统通过回答约束尽量避免编造企业政策。



\### 4.2 智能工单创建



员工描述 IT 故障。



系统支持两种工单规划模式：



\- rule：通过规则构建工单草稿

\- llm：使用 Qwen3 生成结构化工单草稿



工具调用产生的参数不能绕过后端业务校验和人工审批。



\### 4.3 人工审批



工单提交后进入 pending\_approval 状态。



管理员可以：



\- 查询待审批工作流

\- 查看工单草稿

\- 批准工单

\- 拒绝工单

\- 查询正式数据库工单



批准后，系统写入 SQLite。



拒绝后，不创建正式工单。



\### 4.4 持久化和幂等性



使用 SQLite 保存工单。



使用 request\_id 作为业务幂等标识，避免相同操作重复创建工单。



使用 SQLite Checkpointer 保存 LangGraph 状态，支持跨进程恢复审批工作流。



\### 4.5 API 身份验证



员工接口使用独立的员工 API Key。



审批接口使用独立的管理员 API Key。



密钥由服务端环境变量配置。



当前属于本地演示级认证，不提供真实用户登录、RBAC 或完整审计体系。



\## 5. 本地运行



\### 环境要求



\- Windows

\- Python 虚拟环境

\- Ollama

\- Qwen3:8b

\- BGE-M3



\### 配置



在项目根目录创建 `.env`，填写模型、数据库和 API 认证配置。



参考后续提供的 `.env.example`。



不要将真实密钥提交到代码仓库。



\### 启动



完成环境配置后，双击：



`start-opsdesk.cmd`



启动程序检查 Ollama、FastAPI 和 Streamlit。



服务地址：



| 服务 | 地址 |

|---|---|

| Ollama | http://127.0.0.1:11434 |

| FastAPI | http://127.0.0.1:8000 |

| Swagger | http://127.0.0.1:8000/docs |

| Streamlit | http://127.0.0.1:8501 |



当前 Windows 启动程序依赖本机 Ollama 启动脚本路径，迁移设备时需要调整配置。



\## 6. 主要 API



| 方法 | 路径 | 作用 |

|---|---|---|

| GET | /health | 服务健康检查 |

| POST | /api/knowledge/ask | RAG 问答 |

| POST | /api/tickets | 提交待审批工单 |

| GET | /api/tickets/workflows/{thread\_id} | 查询工作流 |

| POST | /api/tickets/workflows/{thread\_id}/decision | 批准或拒绝 |

| GET | /api/tickets/{ticket\_id} | 查询正式工单 |



接口参数及响应格式可通过 Swagger 查看。



\## 7. 测试



项目包含针对以下能力的测试：



\- RAG 检索与问答

\- 工单 SQLite 存储

\- 幂等性处理

\- LangGraph 人工审批

\- SQLite Checkpoint 跨进程恢复

\- FastAPI 身份验证

\- 真实 Qwen3 Tool Calling

\- HTTP 端到端工单流程



已执行过的代表性测试命令：



```powershell

.\\.venv\\Scripts\\python.exe -m scripts.test\_ticket\_store



.\\.venv\\Scripts\\python.exe -m scripts.test\_checkpoint\_restart



.\\.venv\\Scripts\\python.exe -m scripts.test\_api\_tickets



.\\.venv\\Scripts\\python.exe -m scripts.test\_api\_live\_e2e

```



真实模型测试需要 Ollama 服务及对应模型可用。



\## 8. 当前限制



这是用于学习与面试展示的本地项目，不是生产级企业 IT 系统。



当前限制包括：



\- API Key 不对应真实员工身份

\- 缺少完整 RBAC 与审计日志

\- 管理员通过 thread\_id 查询工作流

\- 知识问答引用尚未实现自动事实核验

\- 前端聊天记录主要依赖 Streamlit Session State

\- 不保证浏览器会话结束后保留聊天历史

\- 长时间运行的问答尚未实现独立后台任务管理



\## 9. 后续改进



\- 增加真正的用户身份认证和角色权限

\- 实现待审批工单列表

\- 完善异步任务与状态查询

\- 增加 RAG 检索与回答质量评估

\- 完善日志、监控与异常处理

\- 增加自动化部署能力



\## 10. 项目定位



本项目重点展示：



1\. Agent 工作流编排

2\. RAG 检索增强生成

3\. Tool Calling 与结构化业务操作

4\. 人工审批和权限边界

5\. 状态持久化与幂等性

6\. 前后端集成与测试