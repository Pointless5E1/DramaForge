/**
 * 指令執行器
 * 
 * 負責將後端發送的指令應用到數據對象。
 * 所有校驗已在後端完成，這裏只負責機械地執行指令。
 */

import { set, get } from 'lodash-es'
import type { Instruction } from '@renderer/types/instruction'

/**
 * 指令執行器類
 */
export class InstructionExecutor {
  private data: Record<string, any> = {}

  /**
   * 創建執行器
   * @param initialData 初始數據
   */
  constructor(initialData: Record<string, any> = {}) {
    this.data = { ...initialData }
  }

  /**
   * 執行單條指令
   * @param instruction 指令對象
   */
  execute(instruction: Instruction): void {
    switch (instruction.op) {
      case 'set':
        this.executeSet(instruction.path, instruction.value)
        break
      case 'append':
        this.executeAppend(instruction.path, instruction.value)
        break
      case 'done':
        // done 指令無需執行
        break
    }
  }

  /**
   * 執行 set 指令
   * @param path JSON Pointer 路徑
   * @param value 要設置的值
   */
  private executeSet(path: string, value: any): void {
    const lodashPath = this.convertPath(path)
    set(this.data, lodashPath, value)
  }

  /**
   * 執行 append 指令
   * @param path JSON Pointer 路徑
   * @param value 要追加的元素
   */
  private executeAppend(path: string, value: any): void {
    const lodashPath = this.convertPath(path)
    const arr = get(this.data, lodashPath) || []
    
    if (!Array.isArray(arr)) {
      console.warn(`路徑 ${path} 不是數組，無法執行 append 操作`)
      return
    }
    
    arr.push(value)
    set(this.data, lodashPath, arr)
  }

  /**
   * 將 JSON Pointer 路徑轉換爲 lodash 路徑
   * @param pointer JSON Pointer 格式（如 /name 或 /config/theme）
   * @returns lodash 路徑格式（如 name 或 config.theme）
   */
  private convertPath(pointer: string): string {
    // 移除開頭的 /
    if (pointer.startsWith('/')) {
      pointer = pointer.slice(1)
    }
    
    // 將 / 替換爲 .
    return pointer.replace(/\//g, '.')
  }

  /**
   * 獲取當前數據
   * @returns 數據對象
   */
  getData(): Record<string, any> {
    return this.data
  }

  /**
   * 重置數據
   * @param newData 新數據
   */
  reset(newData: Record<string, any> = {}): void {
    this.data = { ...newData }
  }

  /**
   * 清空數據
   */
  clear(): void {
    this.data = {}
  }
}
