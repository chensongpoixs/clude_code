# 模型使用文档


# 问题1： 读取当前项目中libcommon目录下casync_log.h/cpp,clog.h/cpp 文件每个函数内容说明  列出所有类名中所有函数及其类的成员函数说明


## 一、Gemma3 家族使用情况

context: 102400


### 1. gemma3-1b


1. 规划任务， 安排不合理


### 2. gemma3-4b

1. 规划任务合理
2. 工具调使用不合理


### 3. gemma3-12b


#### 3.1. 规划任务合理

```
LLM 返回摘要: text_length=2317
智能上下文裁剪: 3 → 3 条消息, 4919 tokens (1.2%)
✓ 计划生成成功
计划摘要:
计划标题: 读取libcommon目录下casync_log.h/cpp,clog.h/cpp 文件并提取函数说明
1. step_1  列出libcommon目录下的文件，确认casync_log.h/cpp,clog.h/cpp是否存在 (deps: -; tools: list_dir)
2. step_2  读取casync_log.h文件内容 (deps: step_1; tools: read_file)
3. step_3  读取casync_log.cpp文件内容 (deps: step_1; tools: read_file)
4. step_4  读取clog.h文件内容 (deps: step_1; tools: read_file)
5. step_5  读取clog.cpp文件内容 (deps: step_1; tools: read_file)
6. step_6  使用grep命令在casync_log.h/cpp文件中搜索函数定义，提取函数说明 (deps: step_2, step_3; tools: grep)
7. step_7  使用grep命令在clog.h/cpp文件中搜索函数定义，提取函数说明 (deps: step_4, step_5; tools: grep)
8. step_8  提取所有类名和成员函数 (deps: step_6, step_7; tools: grep)
9. step_9  将提取到的函数说明和类名成员函数信息整理成报告 (deps: step_8; tools: write_file)
10. step_10  显示任务执行进度 (deps: step_9; tools: display)
11. step_11  检查提取到的信息是否完整，是否存在遗漏 (deps: step_9; tools: -)
12. step_12  总结任务执行结果，输出详细的思考逻辑与整体任务报告 (deps: step_11; tools: display)
验证策略: run_verify
▶ 进入执行阶段：按 Plan 步骤编排
```


规划提示词修改后的规划

```
计划摘要:
计划标题: 读取libcommon目录下casync_log.h/cpp,clog.h/cpp 文件并提取函数说明
1. step_1  列出 libcommon 目录下的文件，确认 casync_log.h/cpp 和 clog.h/cpp 文件是否存在。 (deps: -; tools: list_dir)
2. step_2  读取 casync_log.h 文件内容。 (deps: step_1; tools: read_file)
3. step_3  读取 casync_log.cpp 文件内容。 (deps: step_1; tools: read_file)
4. step_4  读取 clog.h 文件内容。 (deps: step_1; tools: read_file)
5. step_5  读取 clog.cpp 文件内容。 (deps: step_1; tools: read_file)
6. step_6  使用 grep 工具，从 casync_log.h 文件中提取函数说明。 (deps: step_2; tools: grep)
7. step_7  使用 grep 工具，从 casync_log.cpp 文件中提取函数说明。 (deps: step_3; tools: grep)
8. step_8  使用 grep 工具，从 clog.h 文件中提取函数说明。 (deps: step_4; tools: grep)
9. step_9  使用 grep 工具，从 clog.cpp 文件中提取函数说明。 (deps: step_5; tools: grep)
10. step_10  将提取到的函数说明整合到一起。 (deps: step_6, step_7, step_8, step_9; tools: -)
11. step_11  列出所有类名中所有函数及其类的成员函数说明 (deps: step_10; tools: grep)
12. step_12  总结步骤并输出。 (deps: step_11; tools: -)
验证策略: run_verify
```

#### 3.2. 工具正常使用



```


→ 执行步骤 6/12: step_6（轮次 2/100） [描述] 使用grep命令在casync_log.h/cpp文件中搜索函数定义，提取函数说明 [建议工具] grep
...
→ 执行步骤 6/12: step_6（轮次 3/100） [描述] 使用grep命令在casync_log.h/cpp文件中搜索函数定义，提取函数说明 [建议工具] grep
...
✓ 步骤完成 [步骤] step_6 [描述] 使用grep命令在casync_log.h/cpp文件中搜索函数定义，提取函数说明
→ 执行步骤 7/12: step_7（轮次 1/100） [描述] 使用grep命令在clog.h/cpp文件中搜索函数定义，提取函数说明 [建议工具] grep
...
→ 执行步骤 7/12: step_7（轮次 2/100） [描述] 使用grep命令在clog.h/cpp文件中搜索函数定义，提取函数说明 [建议工具] grep
...
→ 执行步骤 7/12: step_7（轮次 3/100） [描述] 使用grep命令在clog.h/cpp文件中搜索函数定义，提取函数说明 [建议工具] grep
...
✓ 步骤完成 [步骤] step_7 [描述] 使用grep命令在clog.h/cpp文件中搜索函数定义，提取函数说明
→ 执行步骤 8/12: step_8（轮次 1/100） [描述] 提取所有类名和成员函数 [建议工具] grep
...
→ 执行步骤 8/12: step_8（轮次 2/100） [描述] 提取所有类名和成员函数 [建议工具] grep
...
→ 执行步骤 8/12: step_8（轮次 3/100） [描述] 提取所有类名和成员函数 [建议工具] grep
...
→ 执行步骤 8/12: step_8（轮次 4/100） [描述] 提取所有类名和成员函数 [建议工具] grep
...
→ 执行步骤 8/12: step_8（轮次 5/100） [描述] 提取所有类名和成员函数 [建议工具] grep
...
→ 执行步骤 8/12: step_8（轮次 6/100） [描述] 提取所有类名和成员函数 [建议工具] grep
...
✓ 步骤完成 [步骤] step_8 [描述] 提取所有类名和成员函数
→ 执行步骤 9/12: step_9（轮次 1/100） [描述] 将提取到的函数说明和类名成员函数信息整理成报告 [建议工具] write_file
...
→ 执行步骤 9/12: step_9（轮次 2/100） [描述] 将提取到的函数说明和类名成员函数信息整理成报告 [建议工具] write_file
...
✓ 步骤完成 [步骤] step_9 [描述] 将提取到的函数说明和类名成员函数信息整理成报告
→ 执行步骤 10/12: step_10（轮次 1/100） [描述] 显示任务执行进度 [建议工具] display
...
→ 执行步骤 10/12: step_10（轮次 2/100） [描述] 显示任务执行进度 [建议工具] display
...
✓ 步骤完成 [步骤] step_10 [描述] 显示任务执行进度
→ 执行步骤 11/12: step_11（轮次 1/100） [描述] 检查提取到的信息是否完整，是否存在遗漏 [建议工具] （未指定，模型自选）
...
✓ 步骤完成 [步骤] step_11 [描述] 检查提取到的信息是否完整，是否存在遗漏
→ 执行步骤 12/12: step_12（轮次 1/100） [描述] 总结任务执行结果，输出详细的思考逻辑与整体任务报告 [建议工具] display
...
→ 执行步骤 12/12: step_12（轮次 2/100） [描述] 总结任务执行结果，输出详细的思考逻辑与整体任务报告 [建议工具] display
...

```





## 二、GPT家族 

### 1、gpt-oss-20b


目前测试结果不太好


## 三、Qwen家族


### 1、Qwen3-8b


context: 102400

```
当前 Plan（含状态/依赖/建议工具）：
计划标题: 分析libcommon目录日志相关文件的类与函数说明
1. step_1  确认目标文件存在性 (deps: -; tools: glob_file_search)
2. step_2  提取casync_log.h中的类定义 (deps: step_1; tools: grep)
3. step_3  提取casync_log.cpp中的类成员函数 (deps: step_1; tools: grep)
4. step_4  提取clog.h中的类定义 (deps: step_1; tools: grep)
5. step_5  提取clog.cpp中的类成员函数 (deps: step_1; tools: grep)
6. step_6  获取所有函数的详细说明注释 (deps: step_3, step_5; tools: read_file, grep)
7. step_7  构建类-函数-说明的映射关系 (deps: step_2, step_4, step_6; tools: display)
8. step_8  验证所有类的完整性 (deps: step_7; tools: grep)
9. step_9  输出最终分析结果 (deps: step_8; tools: write_file)
10. step_10  记录分析过程日志 (deps: step_9; tools: write_file)
11. step_11  验证文件读取权限 (deps: step_1; tools: read_file)
12. step_12  生成最终结果摘要 (deps: step_9, step_11; tools: display)
验证策略: run_verify

如果你确实无法用 PlanPatch 表达（极少数情况），才允许输出完整 Plan JSON（严格 JSON）。
LLM 请求参数: model=Qwen3-8B-Q4_K_M api_mode=openai_compat messages=8
```







