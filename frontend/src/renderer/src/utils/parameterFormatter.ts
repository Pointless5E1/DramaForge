/**
 * 參數值格式化工具
 * 
 * 統一處理工作流節點參數的格式化邏輯
 */

export interface ParameterFormatOptions {
  type: string // 參數類型：string, integer, number, boolean, etc.
  value: any   // 原始值
}

export class ParameterFormatter {
  private static escapeString(value: any): string {
    const text = String(value)
    return text
      .replace(/\\/g, '\\\\')
      .replace(/\r/g, '\\r')
      .replace(/\n/g, '\\n')
      .replace(/\t/g, '\\t')
      .replace(/"/g, '\\"')
  }
  /**
   * 檢測是否是變量引用
   * 格式：變量名.屬性名 (例如: text.content, novel.chapter_list)
   */
  static isVariableReference(value: any): boolean {
    if (value === null || value === undefined) return false
    const strValue = String(value)
    return /^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)+$/.test(strValue)
  }

  /**
   * 檢測值是否爲空
   * 注意：0 和 false 不算空值
   */
  static isEmpty(value: any): boolean {
    if (value === 0 || value === false) return false
    if (value === null || value === undefined) return true
    
    const strValue = String(value).trim()
    return strValue === ''
  }

  /**
   * 格式化參數值爲 Python 代碼
   */
  static format(options: ParameterFormatOptions): string {
    const { type, value } = options

    // 空值處理
    if (this.isEmpty(value)) {
      return ''
    }

    // 變量引用：直接使用（解析器會自動添加 $ 標記）
    if (this.isVariableReference(value)) {
      return String(value)
    }

    // 根據類型格式化
    let result: string
    switch (type) {
      case 'integer':
      case 'number':
        result = String(value)
        break

      case 'boolean':
        // 轉換爲 Python 布爾值
        result = (value === 'true' || value === true) ? 'True' : 'False'
        break

      case 'string':
        // 字符串：加引號，轉義特殊字符
        result = `"${this.escapeString(value)}"`
        break

      case 'array':
        // 數組類型：支持數組或逗號分隔的字符串
        if (Array.isArray(value)) {
          // 直接是數組
          const items = value.map(item => `"${this.escapeString(item)}"`)
          result = `[${items.join(', ')}]`
        } else if (typeof value === 'string') {
          // 逗號分隔的字符串，轉換爲數組
          const items = value.split(',').map(item => item.trim()).filter(item => item)
          result = `[${items.map(item => `"${this.escapeString(item)}"`).join(', ')}]`
        } else {
          result = this.formatComplexType(value)
        }
        break
      
      case 'object':
        // 複雜類型：JSON 序列化（需要轉換爲 Python 格式）
        result = this.formatComplexType(value)
        break

      default:
        // 未知類型：檢查是否是對象
        if (typeof value === 'object' && value !== null) {
          result = this.formatComplexType(value)
        } else {
          // 默認當作字符串處理
          result = `"${this.escapeString(value)}"`
        }
        break
    }
    
    // 最終安全檢查：確保返回字符串
    if (typeof result !== 'string') {
      console.error('[ParameterFormatter.format] 結果不是字符串！強制轉換:', result)
      result = JSON.stringify(result)
    }
    
    return result
  }

  /**
   * 格式化複雜類型（數組、對象）
   */
  private static formatComplexType(value: any): string {
    if (Array.isArray(value)) {
      const items = value.map(item => {
        // 遞歸格式化數組元素
        if (typeof item === 'object' && item !== null) {
          return this.formatComplexType(item)
        } else if (typeof item === 'string') {
          return `"${this.escapeString(item)}"`
        } else if (typeof item === 'number') {
          return String(item)
        } else if (typeof item === 'boolean') {
          return item ? 'True' : 'False'
        } else {
          return `"${this.escapeString(item)}"`
        }
      })
      return `[${items.join(', ')}]`
    }

    if (typeof value === 'object' && value !== null) {
      const pairs = Object.entries(value).map(([key, val]) => {
        // 遞歸格式化對象值
        let formattedVal: string
        if (typeof val === 'object' && val !== null) {
          formattedVal = this.formatComplexType(val)
        } else if (typeof val === 'string') {
          formattedVal = `"${this.escapeString(val)}"`
        } else if (typeof val === 'number') {
          formattedVal = String(val)
        } else if (typeof val === 'boolean') {
          formattedVal = val ? 'True' : 'False'
        } else {
          formattedVal = `"${this.escapeString(val)}"`
        }
        return `"${key}": ${formattedVal}`
      })
      return `{${pairs.join(', ')}}`
    }

    return String(value)
  }

  /**
   * 解析顯示值（去掉引號）
   */
  static parseDisplayValue(value: any): string {
    if (value === null || value === undefined) return ''

    // 處理對象類型（字典）
    if (typeof value === 'object' && !Array.isArray(value)) {
      try {
        // 轉換爲 Python 字典格式
        return this.formatComplexType(value)
      } catch (e) {
        return JSON.stringify(value)
      }
    }

    // 處理數組類型
    if (Array.isArray(value)) {
      try {
        return this.formatComplexType(value)
      } catch (e) {
        return JSON.stringify(value)
      }
    }

    let strValue = String(value)

    // 去掉字符串引號
    if ((strValue.startsWith('"') && strValue.endsWith('"')) ||
        (strValue.startsWith("'") && strValue.endsWith("'"))) {
      return strValue.substring(1, strValue.length - 1)
    }

    return strValue
  }
}
