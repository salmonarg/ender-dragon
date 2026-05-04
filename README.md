# EnderDragon_agent 正式版重构

## 项目地址
[Endra](https://github.com/yyywaa/EnderDragon_agent)

## 关于原来的一坨

我们先不讨论关于网络处理的问题，我们只讨论agent架构就存在很大的问题，几乎可以用原始来形容以前的做法。强依赖判断模型的输出，不仅不够智能稳定，还存在注入风险。
本仓库的代码实现依赖于[chatroom](https://github.com/salmonarg/chatroom),感谢khangai为本项目作出的贡献，让我们不必更多考虑关于session鉴权的问题。

## 项目介绍

本仓库实现了一个在minecraft服务器以及聊天室中活跃的末影龙聊天机器人。

### 上下文处理

对于每一条json，将会删减至仅包含以下字段（为防止上下文拥堵）：
{
"sender_username":"EnderDragon",
"text":"Dragon roars.",
"time":处理后的timestamp数据,
"msg_id":"msg-6767676767676-abcde"
}
msg_id需要保留，方便agent调用工具删除一些自己的消息用。

### tool_call实现

之前的双模型模式依旧可以沿用下来，但是判断模型只允许注册连接回复模型的工具：

sent2brain:{"is_need_reply": boolean}

而回复模型可以有这些工具：

sent:{"msg_content": str, "channel": str}
delete:{"msg_id": str, "channel": str}
模型直接输出的内容不作捕获，仅仅作为思考链和调试工具。

如此第一个判断模型的prompt大幅衰减，甚至都不需要赋予是否。

以上均为输入格式json会转成openai格式进行传输。



