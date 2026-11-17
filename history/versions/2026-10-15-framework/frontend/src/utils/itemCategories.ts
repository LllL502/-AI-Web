export interface ItemCategory {
  id: number
  name: string
  code: string
  parent_id: number | null
}

export type ItemCategoryIcon = 'laptop' | 'card' | 'book' | 'key' | 'box'

// 顺序与后端类别字典一致，首页和广场共用这一份规则。
const ROOT_CATEGORY_ORDER = ['digital', 'cards', 'study', 'daily', 'personal']
const ROOT_CATEGORY_ICONS: Record<string, ItemCategoryIcon> = {
  digital: 'laptop',
  cards: 'card',
  study: 'book',
  daily: 'key',
  personal: 'box',
}

export function rootItemCategories(categories: ItemCategory[]): ItemCategory[] {
  return categories
    .filter((entry) => entry.parent_id === null)
    .sort((left, right) => {
      const leftIndex = ROOT_CATEGORY_ORDER.indexOf(left.code)
      const rightIndex = ROOT_CATEGORY_ORDER.indexOf(right.code)
      const normalizedLeft = leftIndex === -1 ? ROOT_CATEGORY_ORDER.length : leftIndex
      const normalizedRight = rightIndex === -1 ? ROOT_CATEGORY_ORDER.length : rightIndex
      return normalizedLeft - normalizedRight || left.name.localeCompare(right.name, 'zh-CN')
    })
}

export function itemCategoryIcon(categoryCode: string): ItemCategoryIcon {
  return ROOT_CATEGORY_ICONS[categoryCode] ?? 'box'
}
