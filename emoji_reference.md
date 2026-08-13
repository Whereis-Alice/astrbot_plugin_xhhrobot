# 小黑盒表情对照表

本表记录插件内置的 156 个小黑盒标准表情标识符，快照日期为 2026-08-11。发送时应优先使用表中的完整标记，例如 `[cube_doge]`。

运行时，插件会先读取当前登录账号的 `/bbs/app/api/emojis/list` 返回值；该实时列表优先于本表。若接口暂时不可用，才使用本表作为离线兜底。可以调用 `xhh_get_emojis` 查看当前账号实际返回的名称。

| 表情包 | 标准标识符数 | 标记格式 |
| --- | ---: | --- |
| `cube` | 100 | `[cube_标识符]` |
| `heygirl` | 24 | `[heygirl_标识符]` |
| `bigemoji` | 16 | `[bigemoji_标识符]` |
| `grandemoji` | 16 | `[grandemoji_标识符]` |

## 输入兼容

插件会对完整标记的包名和标识符做大小写与全半角归一化，并兼容每个标准标记的常见中文、英文和历史叫法。发送前会转换为当前账号可用的实际标识符。

| 输入示例 | 发送时的标准标记 |
| --- | --- |
| `[cube_狗头]`、`[cube_doghead]`、`[cube_shiba]` | `[cube_doge]` |
| `[cube_吐血]`、`[cube_vomit]`、`[cube_puke]` | `[cube_吐]` |
| `[cube_剑星涂鸦]`、`[cube_stellar_blade_raven]` | `[cube_剑星渡鸦]` |
| `[heygirl_耶嘿]`、`[heygirl_ehehe]`、`[heygirl_yehey]` | `[heygirl_诶嘿]` |
| `[heygirl_milk_tea]` | `[heygirl_喝奶茶]` |
| `[bigemoji_melon]` | `[bigemoji_吃瓜]` |
| `[grandemoji_all_powerful_heybox_girl]` | `[grandemoji_万能盒娘]` |

只会兼容带包名前缀的完整标记，例如 `[cube_doge]`。未知标记不会凭语义猜测，插件会降级为可读的普通文本，避免把错误表情发到小黑盒。

## `cube`

| 标准标记 | 标准标记 | 标准标记 | 标准标记 |
| --- | --- | --- | --- |
| `[cube_+1]` | `[cube_-1]` | `[cube_2023]` | `[cube_2024]` |
| `[cube_2025]` | `[cube_2026]` | `[cube_doge]` | `[cube_H币]` |
| `[cube_P的谎言]` | `[cube_wota]` | `[cube_爱心]` | `[cube_比心]` |
| `[cube_比耶]` | `[cube_闭嘴]` | `[cube_并不简单]` | `[cube_菜doge]` |
| `[cube_沧桑]` | `[cube_超人]` | `[cube_炒菜]` | `[cube_吃瓜]` |
| `[cube_吃鸡啦]` | `[cube_吹口哨]` | `[cube_打脸]` | `[cube_打咩]` |
| `[cube_蛋糕]` | `[cube_点赞]` | `[cube_电牛]` | `[cube_鹅]` |
| `[cube_感动]` | `[cube_咕咕]` | `[cube_鼓掌]` | `[cube_乖]` |
| `[cube_害羞]` | `[cube_汗]` | `[cube_盒十]` | `[cube_黑人问号]` |
| `[cube_红包]` | `[cube_滑稽]` | `[cube_毁灭战士]` | `[cube_鸡毙你]` |
| `[cube_加油]` | `[cube_剑星渡鸦]` | `[cube_剑星伊芙]` | `[cube_僵尸]` |
| `[cube_惊讶]` | `[cube_开心]` | `[cube_哭泣]` | `[cube_酷]` |
| `[cube_困]` | `[cube_来财]` | `[cube_浪人砍一刀]` | `[cube_良民]` |
| `[cube_灵光一闪]` | `[cube_洛的点赞]` | `[cube_马年吉祥]` | `[cube_玫瑰]` |
| `[cube_猛男微笑]` | `[cube_摸摸头]` | `[cube_你懂我]` | `[cube_柠檬]` |
| `[cube_怒]` | `[cube_欧润吉]` | `[cube_喷水]` | `[cube_碰拳]` |
| `[cube_凄凉]` | `[cube_庆祝]` | `[cube_庆祝-圣诞]` | `[cube_山姆无奈]` |
| `[cube_上学-乐]` | `[cube_上学-丧]` | `[cube_生气]` | `[cube_圣诞树]` |
| `[cube_时间旅者]` | `[cube_睡觉]` | `[cube_太酷啦]` | `[cube_摊手]` |
| `[cube_叹气]` | `[cube_吐]` | `[cube_哇]` | `[cube_微笑]` |
| `[cube_委屈]` | `[cube_窝囊]` | `[cube_我懂你]` | `[cube_我方了]` |
| `[cube_握草]` | `[cube_捂脸哭]` | `[cube_悟空]` | `[cube_嬉水女王]` |
| `[cube_喜+1]` | `[cube_喜欢]` | `[cube_吓]` | `[cube_小鸡]` |
| `[cube_笑cry]` | `[cube_学习]` | `[cube_阳]` | `[cube_耶]` |
| `[cube_晕]` | `[cube_赞]` | `[cube_摘墨镜]` | `[cube_这是什么鸟]` |

## `heygirl`

| 标准标记 | 标准标记 | 标准标记 | 标准标记 |
| --- | --- | --- | --- |
| `[heygirl_rua!]` | `[heygirl_挨刀]` | `[heygirl_白嫖怪]` | `[heygirl_吃瓜]` |
| `[heygirl_痴]` | `[heygirl_诶嘿]` | `[heygirl_哈哈]` | `[heygirl_害羞]` |
| `[heygirl_喝奶茶]` | `[heygirl_滑稽]` | `[heygirl_记下来]` | `[heygirl_惊]` |
| `[heygirl_开可乐]` | `[heygirl_哭]` | `[heygirl_苦酒入喉]` | `[heygirl_捏脸]` |
| `[heygirl_敲开心]` | `[heygirl_茄化]` | `[heygirl_偷看]` | `[heygirl_秃]` |
| `[heygirl_无语]` | `[heygirl_喜欢]` | `[heygirl_疑问]` | `[heygirl_这…]` |

## `bigemoji`

| 标准标记 | 标准标记 | 标准标记 | 标准标记 |
| --- | --- | --- | --- |
| `[bigemoji_？]` | `[bigemoji_暗中观察]` | `[bigemoji_比心]` | `[bigemoji_吃瓜]` |
| `[bigemoji_打折]` | `[bigemoji_风纪委员]` | `[bigemoji_哈哈]` | `[bigemoji_滑稽]` |
| `[bigemoji_开可乐]` | `[bigemoji_厉害]` | `[bigemoji_求带]` | `[bigemoji_摔]` |
| `[bigemoji_委屈]` | `[bigemoji_喜加一]` | `[bigemoji_羡慕]` | `[bigemoji_做梦]` |

## `grandemoji`

| 标准标记 | 标准标记 | 标准标记 | 标准标记 |
| --- | --- | --- | --- |
| `[grandemoji_awsl]` | `[grandemoji_mur化]` | `[grandemoji_痴]` | `[grandemoji_盒弹来袭]` |
| `[grandemoji_交个朋友]` | `[grandemoji_摸不着头脑]` | `[grandemoji_爬]` | `[grandemoji_爬了]` |
| `[grandemoji_啥玩意]` | `[grandemoji_缩]` | `[grandemoji_躺平]` | `[grandemoji_万能盒娘]` |
| `[grandemoji_我很可爱]` | `[grandemoji_呀嘞呀嘞]` | `[grandemoji_整挺好]` | `[grandemoji_做个好梦]` |

## 维护说明

小黑盒可能按客户端版本、账号或活动调整表情列表。新增或变化的表情以当前账号的实时列表为准；需要更新离线兜底时，同时修改 `emoji_catalog.py`、本表与对应单元测试。
