const INTERNAL_CARD_TYPE_NAMES = new Set(['劇本片段正文'])

interface CardLike {
  card_type?: { name?: string | null } | null
}

interface CardTypeLike {
  name?: string | null
}

export function isInternalCardFacet(card: CardLike | null | undefined): boolean {
  return INTERNAL_CARD_TYPE_NAMES.has(String(card?.card_type?.name || ''))
}

export function isVisibleCardType(type: CardTypeLike | null | undefined): boolean {
  return !INTERNAL_CARD_TYPE_NAMES.has(String(type?.name || ''))
}

export function visibleCardTypeLabel(name: string | null | undefined): string {
  return name === '劇本片段大綱' ? '劇本片段' : String(name || '未知類型')
}
