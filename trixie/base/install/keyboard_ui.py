"""Terminal keyboard selection using the installed XKB registry."""

COMMON = (('fi', 'Finnish'), ('se', 'Swedish'), ('de', 'German'),
          ('us', 'English (US)'), ('gb', 'English (UK)'))
PAGE_SIZE = 12


def choose_layout(layouts, read=input):
    common = [(code, title) for code, title in COMMON if code in layouts]
    while True:
        print('\nKeyboard layout')
        for index, (code, title) in enumerate(common, 1):
            print(f'  {index}. {title} ({code})' + (' – default' if code == 'fi' else ''))
        browse = len(common) + 1
        print(f'  {browse}. Show all available keyboard layouts')
        answer = read('Selection [1] (or enter a layout code): ').strip().lower()
        if not answer:
            if common:
                return common[0][0]
            answer = str(browse)
        if answer in layouts:
            return answer
        if answer.isascii() and answer.isdecimal() and len(answer) <= 4 and 1 <= int(answer) <= len(common):
            return common[int(answer) - 1][0]
        if answer in (str(browse), 'all', 'list', 'help', '?'):
            selected = browse_layouts(layouts, read)
            if selected:
                return selected
        else:
            print('Invalid selection. Enter a listed number, an XKB layout code, or show all layouts.')


def browse_layouts(layouts, read):
    query = ''
    page = 0
    while True:
        matches = sorted(((code, name) for code, name in layouts.items()
                          if query in code.casefold() or query in name.casefold()),
                         key=lambda item: (item[1].casefold(), item[0]))
        pages = max(1, (len(matches) + PAGE_SIZE - 1) // PAGE_SIZE)
        start = page * PAGE_SIZE
        print(f'\nAvailable layouts · page {page + 1}/{pages}' + (f' · filter: {query}' if query else ''))
        if not matches:
            print('  No matching layouts.')
        for number, (code, name) in enumerate(matches[start:start + PAGE_SIZE], start + 1):
            print(f'  {number:3}. {name} ({code})')
        print('  [n] Next  [p] Previous  [s] Search  [c] Clear filter  [b] Back')
        choice = read('Layout number or action: ').strip().lower()
        if choice in ('b', 'back'):
            return None
        if choice in ('s', 'search', 'c', 'clear') or choice.startswith('/'):
            if choice in ('s', 'search'):
                query = read('Search by code or name (blank clears): ').strip().casefold()
            else:
                query = choice[1:].strip().casefold() if choice.startswith('/') else ''
            page = 0
        elif choice in ('n', 'next') and page + 1 < pages:
            page += 1
        elif choice in ('p', 'prev', 'previous') and page:
            page -= 1
        elif choice.isascii() and choice.isdecimal() and len(choice) <= 6 and start < int(choice) <= min(start + PAGE_SIZE, len(matches)):
            return matches[int(choice) - 1][0]
        else:
            print('Enter a number shown on this page or choose an available action.')
