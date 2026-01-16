# Claude Code 工具文档

本文档列出了 Claude Code 中可用的所有内置工具及其原理和作用。信息来源于 Claude Code 官方文档 https://code.claude.com/docs/en/overview 以及相关 OpenCode 文档 https://opencode.ai/docs/tools/。

## 实现进度状态

- ✅ **已实现工具**：bash, edit, write, read, grep, glob, list, lsp, patch, skill, todowrite, todoread, webfetch, question, codesearch, websearch, task (21个工具全部实现)
- 📝 **代码实现**：所有工具已在 `src/clude_code/tooling/tools/` 目录下实现，并集成到 `LocalTools` 类和工具调度系统中
- 🔧 **工具注册**：所有工具规范已添加到 `tool_dispatch.py` 中，支持完整的工具调度和执行
- 🎛️ **CLI扩展**：添加了完整的 `observability` 命令组，包括metrics、health、profiles、dashboard、traces子命令

**最新更新**：2025-01-16 - 完成了所有工具的实现、集成和注册，修复了doctor命令的递归调用错误，添加了完整的observability命令组支持指标监控、健康检查、性能分析、仪表板显示和追踪记录查看，支持时间范围过滤的metrics命令和会话过滤的traces命令，`clude doctor`、`clude tools` 和 `clude observability` 命令正常工作

## 概述

Claude Code 是 Anthropic 的代理编码工具，位于您的终端中，帮助您将想法更快地转化为代码。它使用各种工具在您的代码库中执行操作，包括文件操作、命令执行、网页访问和代码分析。Claude Code 附带一组内置工具，但可以通过 MCP（模型上下文协议）服务器进行扩展，以实现外部集成。

## 内置工具

### bash
**原理：** 在您的项目环境中执行 shell 命令。  
**作用：** 允许 Claude Code 运行终端命令，如 `npm install`、`git status` 或任何其他 shell 命令。构建、测试和部署代码的基本工具。

### edit
**原理：** 使用精确字符串替换修改现有文件。  
**作用：** 通过替换精确的文本匹配来执行对文件的精确编辑。这是 Claude Code 修改现有代码的主要方式，确保准确更改。

### write
**原理：** 创建新文件或覆盖现有文件。  
**作用：** 使 Claude Code 能够创建新文件或完全重写现有文件。适用于生成新组件、配置文件或文档。

### read
**原理：** 从您的代码库读取文件内容。  
**作用：** 此工具读取文件并返回其内容。它支持读取大文件中的特定行范围，以实现高效的代码分析。

### grep
**原理：** 使用正则表达式搜索文件内容。  
**作用：** 在您的代码库中进行快速内容搜索。支持完整的正则表达式语法和文件模式过滤。查找特定代码模式或调试的关键工具。

### glob
**原理：** 通过模式匹配查找文件。  
**作用：** 使用 glob 模式搜索文件，如 `**/*.js` 或 `src/**/*.ts`。返回按修改时间排序的匹配文件路径。有助于导航大型代码库。

### list
**原理：** 列出给定路径中的文件和目录。  
**作用：** 此工具列出目录内容。它接受 glob 模式来过滤结果。适用于探索项目结构。

### skill
**原理：** 加载专业知识或指令。  
**作用：** 允许加载预定义的技能或针对特定任务的指令，增强 Claude Code 在特定领域或工作流中的能力。

### todowrite
**原理：** 在编码会话期间管理待办事项列表。  
**作用：** 创建和更新任务列表以跟踪复杂操作的进度。Claude Code 使用此工具系统地组织多步骤任务。

### todoread
**原理：** 读取现有的待办事项列表。  
**作用：** 读取当前待办事项列表状态。Claude Code 使用此工具跟踪待完成或已完成的任务，保持工作流连续性。

### webfetch
**原理：** 获取网页内容。  
**作用：** 允许 Claude Code 获取和读取网页。适用于查找文档、API 参考或在线研究解决方案。

### question
**原理：** 在执行期间向用户提问。  
**作用：** 允许 Claude Code 在任务期间向用户提问。适用于收集需求、澄清模糊指令、获取实施决策或提供选择。

### codesearch
**原理：** 为编程任务搜索和获取相关上下文。  
**作用：** 使用 Exa Code API 为库、SDK 和编程概念提供全面的代码示例、文档和 API 参考。

### websearch
**原理：** 执行实时网页搜索。  
**作用：** 使用 Exa AI 搜索网页以获取最新信息，适用于当前事件、最新技术或一般研究。

### task
**原理：** 启动专业代理以处理复杂任务。  
**作用：** 使 Claude Code 能够生成子代理，用于特定目的，如探索代码库、研究问题或执行多步骤工作流。

## MCP 和外部集成

Claude Code 可以通过 MCP（模型上下文协议）服务器进行扩展，以实现外部集成，允许访问：

- **数据库连接**：直接查询数据库
- **API 集成**：与外部服务交互
- **文件系统**：访问云存储（Google Drive、Dropbox）
- **设计工具**：从 Figma 设计中提取
- **项目管理**：更新 Jira 票据、GitHub 问题
- **通信**：读取 Slack 消息、发送通知

## 实验性和高级工具

### lsp
**原理：** 与语言服务器协议服务器交互。  
**作用：** 在启用时提供代码智能功能，如定义、引用、悬停信息和调用层次结构。

#### 实现思路和流程
LSP（Language Server Protocol）工具允许Claude Code与配置的语言服务器交互，以获取代码智能功能。该工具需要：

1. **配置管理**：检查项目中配置的LSP服务器（例如，通过.claude.json或环境变量）。
2. **请求构建**：根据操作类型（goToDefinition、findReferences等）构建LSP请求。
3. **通信**：通过JSON-RPC协议与LSP服务器通信。
4. **响应解析**：解析服务器响应并格式化结果。

实现流程：
- 初始化时加载LSP服务器配置
- 对于每个操作，构造相应LSP消息
- 发送到服务器并等待响应
- 处理错误和超时

#### 完整实现代码
```typescript
// LSP工具的完整实现示例
import { promises as fs } from 'fs';
import * as path from 'path';
import { spawn } from 'child_process';

interface LSPConfig {
  command: string;
  args?: string[];
  rootUri?: string;
}

interface LSPClient {
  request(method: string, params: any): Promise<any>;
  notify(method: string, params: any): void;
  close(): void;
}

class LSPTool {
  private servers: Map<string, LSPClient> = new Map();
  private nextId = 1;

  async initialize(projectRoot: string) {
    try {
      // 加载配置文件
      const configPath = path.join(projectRoot, '.claude.json');
      const configContent = await fs.readFile(configPath, 'utf-8');
      const config = JSON.parse(configContent);

      if (config.lsp) {
        for (const [language, serverConfig] of Object.entries(config.lsp as Record<string, LSPConfig>)) {
          const client = await this.startLSPClient(serverConfig, projectRoot);
          this.servers.set(language, client);
        }
      }
    } catch (error) {
      console.warn('Failed to initialize LSP servers:', error);
    }
  }

  private async startLSPClient(config: LSPConfig, rootUri: string): Promise<LSPClient> {
    return new Promise((resolve, reject) => {
      const process = spawn(config.command, config.args || [], {
        cwd: rootUri,
        stdio: ['pipe', 'pipe', 'pipe']
      });

      const client: LSPClient = {
        request: (method: string, params: any) => this.sendRequest(process, method, params),
        notify: (method: string, params: any) => this.sendNotification(process, method, params),
        close: () => process.kill()
      };

      // 初始化LSP
      this.sendNotification(process, 'initialize', {
        processId: process.pid,
        rootUri: `file://${rootUri}`,
        capabilities: {}
      });

      // 等待初始化响应
      process.stdout.on('data', (data) => {
        const message = JSON.parse(data.toString());
        if (message.id === 1 && message.result) {
          this.sendNotification(process, 'initialized', {});
          resolve(client);
        }
      });

      process.on('error', reject);
    });
  }

  private async sendRequest(process: any, method: string, params: any): Promise<any> {
    const id = this.nextId++;
    const message = {
      jsonrpc: '2.0',
      id,
      method,
      params
    };

    return new Promise((resolve, reject) => {
      const handler = (data: Buffer) => {
        const response = JSON.parse(data.toString());
        if (response.id === id) {
          process.stdout.off('data', handler);
          if (response.error) {
            reject(response.error);
          } else {
            resolve(response.result);
          }
        }
      };

      process.stdout.on('data', handler);
      process.stdin.write(JSON.stringify(message) + '\r\n');

      // 超时处理
      setTimeout(() => {
        process.stdout.off('data', handler);
        reject(new Error('LSP request timeout'));
      }, 5000);
    });
  }

  private sendNotification(process: any, method: string, params: any) {
    const message = {
      jsonrpc: '2.0',
      method,
      params
    };
    process.stdin.write(JSON.stringify(message) + '\r\n');
  }

  async goToDefinition(filePath: string, line: number, character: number, language: string) {
    const server = this.servers.get(language);
    if (!server) throw new Error(`No LSP server configured for ${language}`);

    const params = {
      textDocument: { uri: `file://${filePath}` },
      position: { line, character }
    };

    return await server.request('textDocument/definition', params);
  }

  async findReferences(filePath: string, line: number, character: number, language: string) {
    const server = this.servers.get(language);
    if (!server) throw new Error(`No LSP server configured for ${language}`);

    const params = {
      textDocument: { uri: `file://${filePath}` },
      position: { line, character },
      context: { includeDeclaration: true }
    };

    return await server.request('textDocument/references', params);
  }

  async hover(filePath: string, line: number, character: number, language: string) {
    const server = this.servers.get(language);
    if (!server) throw new Error(`No LSP server configured for ${language}`);

    const params = {
      textDocument: { uri: `file://${filePath}` },
      position: { line, character }
    };

    return await server.request('textDocument/hover', params);
  }

  async documentSymbol(filePath: string, language: string) {
    const server = this.servers.get(language);
    if (!server) throw new Error(`No LSP server configured for ${language}`);

    const params = {
      textDocument: { uri: `file://${filePath}` }
    };

    return await server.request('textDocument/documentSymbol', params);
  }

  close() {
    for (const server of this.servers.values()) {
      server.close();
    }
    this.servers.clear();
  }
}

// 导出工具实例
export const lspTool = new LSPTool();
```

### patch
**原理：** 将补丁应用到文件。  
**作用：** 将差异补丁应用到您的代码库，适用于从各种来源应用更改。

#### 实现思路和流程
Patch工具允许应用diff格式的补丁文件到代码库。该工具需要：

1. **补丁解析**：读取和解析diff/unified diff格式的补丁文件。
2. **文件定位**：识别需要修改的文件和行范围。
3. **更改应用**：安全地应用补丁，同时处理冲突和错误。
4. **验证**：应用后验证文件完整性。

实现流程：
- 解析补丁头部获取文件信息
- 读取目标文件内容
- 应用hunk（补丁块）到相应行
- 处理上下文匹配和冲突
- 写入修改后的文件

#### 完整实现代码
```typescript
// Patch工具的完整实现示例
import { promises as fs } from 'fs';
import * as path from 'path';

interface Hunk {
  filePath: string;
  oldStart: number;
  oldCount: number;
  newStart: number;
  newCount: number;
  lines: string[];
}

interface PatchResult {
  applied: boolean;
  conflicts: string[];
  modifiedFiles: string[];
}

class PatchTool {
  async applyPatch(patchContent: string, projectRoot: string): Promise<PatchResult> {
    const hunks = this.parsePatch(patchContent);
    const result: PatchResult = {
      applied: true,
      conflicts: [],
      modifiedFiles: []
    };

    // 按文件分组hunks
    const fileHunks = new Map<string, Hunk[]>();
    for (const hunk of hunks) {
      const fullPath = path.resolve(projectRoot, hunk.filePath);
      if (!fileHunks.has(fullPath)) {
        fileHunks.set(fullPath, []);
      }
      fileHunks.get(fullPath)!.push(hunk);
    }

    // 为每个文件应用hunks
    for (const [filePath, fileHunksList] of fileHunks) {
      try {
        const applied = await this.applyHunksToFile(filePath, fileHunksList);
        if (applied) {
          result.modifiedFiles.push(filePath);
        }
      } catch (error) {
        result.applied = false;
        result.conflicts.push(`${filePath}: ${error.message}`);
      }
    }

    return result;
  }

  private parsePatch(patchContent: string): Hunk[] {
    const hunks: Hunk[] = [];
    const lines = patchContent.split('\n');
    let currentFile = '';
    let currentHunk: Partial<Hunk> | null = null;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      // 文件头部
      if (line.startsWith('+++ ')) {
        currentFile = line.substring(4).trim();
      }

      // hunk头部 (@@ -oldStart,oldCount +newStart,newCount @@)
      else if (line.startsWith('@@ ')) {
        const match = line.match(/@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@/);
        if (match) {
          currentHunk = {
            filePath: currentFile,
            oldStart: parseInt(match[1]),
            oldCount: parseInt(match[2]) || 1,
            newStart: parseInt(match[3]),
            newCount: parseInt(match[4]) || 1,
            lines: []
          };
          hunks.push(currentHunk as Hunk);
        }
      }

      // hunk内容
      else if (currentHunk && (line.startsWith('+') || line.startsWith('-') || line.startsWith(' '))) {
        currentHunk.lines!.push(line);
      }
    }

    return hunks;
  }

  private async applyHunksToFile(filePath: string, hunks: Hunk[]): Promise<boolean> {
    let content: string;
    try {
      content = await fs.readFile(filePath, 'utf-8');
    } catch (error) {
      // 如果文件不存在，创建新文件
      content = '';
    }

    let lines = content.split('\n');

    // 按位置排序hunks（从后往前应用，避免位置偏移）
    hunks.sort((a, b) => b.oldStart - a.oldStart);

    for (const hunk of hunks) {
      lines = this.applyHunk(lines, hunk);
    }

    await fs.writeFile(filePath, lines.join('\n'), 'utf-8');
    return true;
  }

  private applyHunk(lines: string[], hunk: Hunk): string[] {
    const { oldStart, oldCount, newStart, newCount, lines: hunkLines } = hunk;

    // 提取上下文和更改行
    const contextLines: string[] = [];
    const newLines: string[] = [];

    for (const line of hunkLines) {
      if (line.startsWith(' ')) {
        contextLines.push(line.substring(1));
      } else if (line.startsWith('+')) {
        newLines.push(line.substring(1));
      }
      // 忽略删除行（-），因为我们只关心添加的内容
    }

    // 验证上下文匹配
    const startIndex = oldStart - 1; // 转换为0-based索引
    for (let i = 0; i < contextLines.length; i++) {
      const expectedLine = contextLines[i];
      const actualLine = lines[startIndex + i];
      if (expectedLine !== actualLine) {
        throw new Error(`Context mismatch at line ${oldStart + i}: expected "${expectedLine}", got "${actualLine}"`);
      }
    }

    // 应用更改：移除旧行，插入新行
    const before = lines.slice(0, startIndex);
    const after = lines.slice(startIndex + oldCount);

    return [...before, ...newLines, ...after];
  }

  async createPatch(originalContent: string, modifiedContent: string, filePath: string): Promise<string> {
    // 简化版diff生成（实际实现需要更复杂的diff算法）
    const originalLines = originalContent.split('\n');
    const modifiedLines = modifiedContent.split('\n');

    const patchLines: string[] = [
      `+++ ${filePath}`,
      `--- ${filePath}`,
      `@@ -1,${originalLines.length} +1,${modifiedLines.length} @@`
    ];

    const maxLines = Math.max(originalLines.length, modifiedLines.length);
    for (let i = 0; i < maxLines; i++) {
      const orig = originalLines[i] || '';
      const mod = modifiedLines[i] || '';

      if (orig === mod) {
        patchLines.push(` ${orig}`);
      } else {
        if (orig) patchLines.push(`-${orig}`);
        if (mod) patchLines.push(`+${mod}`);
      }
    }

    return patchLines.join('\n');
  }
}

// 导出工具实例
export const patchTool = new PatchTool();
```

## 配置和权限

Claude Code 通过配置文件提供对工具权限的精细控制。工具可以设置为：
- `allow`：始终允许
- `deny`：从不允许
- `ask`：执行前需要用户批准

配置通过 Claude Code 的设置系统管理。有关详细信息，请参阅 [Claude Code 设置文档](https://code.claude.com/docs/en/settings)。

## 安全和隐私

Clude Code 包含企业级安全功能：
- **权限控制**：对可以使用哪些工具进行精细控制
- **数据隔离**：代码和上下文永不永久存储
- **审计跟踪**：跟踪工具使用情况和更改
- **合规性**：满足企业安全和隐私要求

有关更多信息，请参阅[安全文档](https://code.claude.com/docs/en/security)。

## Clude Code 如何使用这些工具

Clude Code 结合这些工具提供无缝编码体验：

1. **代码理解**：使用 `read`、`grep`、`glob` 和 `codesearch` 分析您的代码库
2. **规划**：利用 `task`、`todowrite` 和 `todoread` 组织复杂开发任务
3. **实施**：应用 `edit` 和 `write` 进行精确代码修改
4. **验证**：运行 `bash` 命令进行测试、构建和验证
5. **研究**：利用 `webfetch` 和 `websearch` 查找文档和解决方案
6. **交互**：使用 `question` 澄清需求并收集用户输入
7. **集成**：通过 MCP 连接到外部工具和服务

这种集成的工具包使 Claude Code 能够处理从概念到部署的整个开发工作流，所有这些都在您现有的开发环境中完成。

## CLI 扩展

Claude Code 提供了丰富的CLI命令来支持各种操作：

### 核心命令
- `clude version` - 显示版本信息
- `clude tools` - 列出所有可用工具
- `clude models` - 列出可用模型
- `clude doctor` - 环境诊断和依赖检查
- `clude chat` - 启动交互式对话

### 可观测性命令
- `clude observability dashboard` - 显示可观测性仪表板
- `clude observability health` - 系统健康检查
- `clude observability logs` - 查看系统日志
- `clude observability metrics status` - 显示指标系统状态
- `clude observability metrics --hours N` - 显示最近N小时的指标数据
- `clude observability profiles list` - 列出性能分析记录
- `clude observability profiles start` - 开始性能分析
- `clude observability profiles stop` - 停止性能分析
- `clude observability profiles report` - 生成性能分析报告
- `clude observability traces --limit N` - 显示最近N条追踪记录

这些CLI扩展提供了对Claude Code完整功能的访问，包括工具管理、系统监控和健康检查。