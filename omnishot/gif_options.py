"""GIF profile controls shared by recording and export."""
WIDTHS=[0,400,600,800,960,1280,1920]
FPS=[5,10,15,24,30,60]


def palette_chain(filters,options):
    quality=max(1,min(100,int(options.get('gif_quality',100))))
    colors=max(4,min(256,round(16+quality*2.4)))
    optimize=bool(options.get('gif_optimize',True))
    use='dither=sierra2_4a'+(':diff_mode=rectangle' if optimize else '')
    return ','.join(filters)+f',split[s0][s1];[s0]palettegen=max_colors={colors}[p];[s1][p]paletteuse={use}'
