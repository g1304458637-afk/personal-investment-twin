# 投镜多人社区：部署与运维

本版本提供独立社区账号、成员可见的投资分享、评论、作者追加跟踪、个人跟踪列表和动态、撤回、服务端持久化与分页。发布前明确预览与展示范围，默认隐藏名称和资金金额。分享的数据由用户提供，不能作为券商核验或第三方认证。

原本地 Demo 保留在 `#/community-demo`，不会自动上传。多人社区入口为 `#/community`。独立服务仅开放社区 API 与静态前端，不开放本机投资账户 RPC、公司研究引擎或 AI 密钥。实际桌面原生联网发布与新的安装包尚未验收；当前交付是浏览器多人版本和服务端部署包。

## 本地运行

在仓库或解压后的服务端包根目录执行（Python 3.11 及以上）：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-community.txt
.venv/bin/python scripts/run_community.py --port 18026
```

源码工作区需要先在 `apps/desktop` 执行 `npm ci`、`npm run build`；部署包已包含构建后的 `apps/desktop/dist`。访问 `http://127.0.0.1:18026/#/community`，分别注册两个社区账号；默认仅监听本机。投镜整合启动器 `scripts/run_integrated_workspace.py` 同样接入此社区存储，保持原 18022 入口。

社区数据库默认位于 `.local/community/community.sqlite3`，与券商/公司研究数据库独立。包内不附带数据库、密码、会话或验收账号。首次启动会建立版本 1 schema；遇到未知版本会停止，不能静默重建旧库。

## 上线配置（本次未部署）

1. 使用独立系统用户 `toujing`。将部署包放入 `/srv/toujing-community`，创建仅该用户可读写的 `/var/lib/toujing-community`（权限 0700）。环境安装依赖后，不再以 root 启动应用。
2. 使用独立域名、有效 HTTPS 证书和反向代理。将 `deploy/community/Caddyfile.example` 的域名替换为实际域名；将 `toujing-community.service.example` 中的 `--origin` 同步修改。
3. 后端仍监听 `127.0.0.1:18026`，仅代理公开 443。应用严格核对 Host、Origin，不信任客户端转发的身份或作者字段。不要把本地 18022 整合服务对公网暴露，也不要代理公司引擎或账户 API。
4. 在另一台设备分别用两个新账号验证发布、评论、跟踪、撤回、退出登录及 HTTPS Cookie，再开放给试用成员。本次只在本机完成验收，不包含域名、TLS、跨设备公网或生产负载测试。
5. 小范围邀请试用可以先完成账号注册，再通过 `--closed-registration` 关闭新注册。不要将本地验收数据库复制到正式环境。当前采用单服务实例 + 本地 SQLite WAL；不支持多个主机共用网络文件系统，也未做大规模并发容量承诺。

当前无邮件验证、自助找回密码、上传任意附件、私信、邮件/推送通知、完整网页审核后台或实名/券商认证。后续动态在页面中读取，可点击刷新。运营方可用下方离线工具禁用账号、撤回违规分享与重置密码；公开大规模运营前仍需补充审核和投诉流程。

## 备份与恢复

服务运行时不能只复制主 sqlite 文件而漏掉 WAL。工具使用 SQLite backup API 生成一致快照，并检查 schema 与 integrity：

```sh
.venv/bin/python scripts/community_admin.py --database /var/lib/toujing-community/community.sqlite3 backup /secure-backups/community-20261023.sqlite3
```

目标文件必须不存在，权限为 0600。备份包含成员提交的内容、密码哈希、会话哈希与跟踪关系，需按私有数据保存；当前没有内置备份加密。

恢复先写入新文件：

```sh
.venv/bin/python scripts/community_admin.py --database /secure-backups/community-20261023.sqlite3 restore-to-new-file /var/lib/toujing-community/community-restored.sqlite3
```

恢复工具检查完整性并清除旧会话，用户需重新登录。停止服务后，将服务配置的 `--database` 指向新文件，启动并验收；保留旧数据库作为回退点。工具不会覆盖正在使用的数据库。

## 账号与内容运维

```sh
.venv/bin/python scripts/community_admin.py --database /var/lib/toujing-community/community.sqlite3 disable-user username
.venv/bin/python scripts/community_admin.py --database /var/lib/toujing-community/community.sqlite3 reset-password username
.venv/bin/python scripts/community_admin.py --database /var/lib/toujing-community/community.sqlite3 withdraw-post 123
```

重置密码通过终端隐藏输入，不接受命令行明文密码；重置或禁用会撤销该账号的全部会话。密码找回应由运营方核对身份，不能仅凭显示名称授予访问。成员名称可以重复，页面同时显示唯一用户名。

撤回是逻辑撤回：其他成员不能再读取该分享、评论和更新；原记录仍在服务器数据库及历史备份中，不能当作物理删除承诺。

## 安全与验证依据

- 密码使用独立随机盐和 scrypt（N=2^15、r=8、p=3）；对应 [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) 的 scrypt 配置。
- 服务器保存会话令牌哈希；浏览器用 HttpOnly、SameSite=Strict Cookie，HTTPS 模式增加 Secure。写操作校验精确 Origin、JSON 类型和会话 CSRF token；会话固定 7 天到期。见 [OWASP Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)。
- 注册、登录和写操作有限流；所有作者与权限来自服务端会话。请求 128 KiB 上限，数据字段白名单、有限数字、合法日期和隐藏字段拦截。外部声明不会被提升为可信收益计算或券商认证。
- 投资分享创建具有幂等请求编号；评论/更新接口同样支持幂等编号。原始账户文件与流水不上传，只有预览选择的数据卡和用户手写文字会发送。

回归命令：

```sh
.venv/bin/python -m pytest tests/test_community.py tests/test_company_research.py -q
npm --prefix apps/desktop test
npm --prefix apps/desktop run build
```

当前进程不信任 `X-Forwarded-For`；在反向代理后，来源 IP 限流按代理地址汇总（另有逐用户名登录限流）。小规模试用可使用默认值，扩大规模前应部署可信边缘限流并进行负载测试，不要直接启用任意转发头信任。
