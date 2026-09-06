"""Zoom track creation, selection and contextual editing."""
import copy


class ZoomActions:
    def select(self,selection):
        self.selected=selection;self.selection_changed.emit();self.update()

    def zoom_gap(self,seconds):
        lo=self.start;hi=self.end or self.duration
        if not lo<=seconds<hi:return None
        for z in self.zooms:
            if z['start']<=seconds<z['end']:return None
            if z['end']<=seconds:lo=max(lo,z['end'])
            if z['start']>seconds:hi=min(hi,z['start'])
        return (lo,hi) if hi-lo>=1/self.fps else None

    def zoom_limits(self,index):
        z=self.zooms[index];lo=0.;hi=self.duration
        for i,other in enumerate(self.zooms):
            if i==index:continue
            if other['end']<=z['start']+1e-7:lo=max(lo,other['end'])
            if other['start']>=z['end']-1e-7:hi=min(hi,other['start'])
        return lo,hi

    def add_zoom_at(self,seconds):
        gap=self.zoom_gap(seconds)
        if gap is None:return None
        lo,hi=gap;minimum=1/self.fps
        a=max(lo,min(hi-minimum,round(seconds*self.fps)/self.fps));b=min(hi,a+3)
        self.editing_focus.emit();self.zooms.append(dict(start=a,end=b,scale=1.5,x=.5,y=.5,follow=True))
        index=len(self.zooms)-1;self.select(('zoom',index));self.seek.emit(round((a+b)*500));self.edited.emit();self.update();return index

    def selected_zoom(self):
        if self.selected and self.selected[0]=='zoom' and self.selected[1]<len(self.zooms):return self.zooms[self.selected[1]]

    def change_zoom(self,**values):
        zoom=self.selected_zoom()
        if zoom is None:return
        self.editing_focus.emit();zoom.update(values);self.edited.emit();self.selection_changed.emit();self.update()

    def apply_zoom_level_to_all(self):
        selected=self.selected_zoom()
        if selected is None:return
        self.editing_focus.emit()
        for zoom in self.zooms:zoom['scale']=selected['scale']
        self.edited.emit();self.update()

    def split_zoom_at_playhead(self):
        if self.drag:self.finish_drag()
        t=round(self.position*self.fps)/self.fps;minimum=1/self.fps-1e-7
        candidate=self.selected_zoom()
        if candidate is None or not candidate['start']+minimum<=t<=candidate['end']-minimum:
            candidate=next((z for z in self.zooms if z['start']+minimum<=t<=z['end']-minimum),None)
        if candidate is None:return False
        self.editing_focus.emit();copy_zoom=copy.deepcopy(candidate);copy_zoom['start']=t;candidate['end']=t;self.zooms.append(copy_zoom)
        self.select(('zoom',len(self.zooms)-1));self.edited.emit();self.update();return True

    def duplicate_zoom(self):
        zoom=self.selected_zoom()
        if zoom is None:return False
        length=zoom['end']-zoom['start'];edges=[zoom['end'],self.start]+[z['end'] for z in self.zooms]
        for a in edges:
            gap=self.zoom_gap(a)
            if gap and gap[1]-a>=length-1e-7:
                duplicate=copy.deepcopy(zoom);duplicate.update(start=a,end=a+length);self.zooms.append(duplicate)
                self.editing_focus.emit();self.select(('zoom',len(self.zooms)-1));self.edited.emit();self.update();return True
        return False

    def zoom_menu(self,menu,index):
        self.editing_focus.emit();self.select(('zoom',index));zoom=self.zooms[index]
        level=menu.addMenu('Zoom Level')
        for value in (100,125,150,175,200,250,300,400,500):
            action=level.addAction(f'{value}%');action.setCheckable(True);action.setChecked(abs(zoom['scale']*100-value)<.01)
            action.triggered.connect(lambda checked=False,v=value:self.change_zoom(scale=v/100))
        menu.addAction('Apply Zoom Level to All',self.apply_zoom_level_to_all);menu.addSeparator()
        mode=menu.addMenu('Zoom Mode')
        for label,follow in [('Follow Cursor',True),('Manual',False)]:
            action=mode.addAction(label);action.setCheckable(True);action.setChecked(bool(zoom.get('follow'))==follow)
            action.triggered.connect(lambda checked=False,v=follow:self.change_zoom(follow=v))
        menu.addSeparator();split=menu.addAction('Split Zoom at Playhead',self.split_zoom_at_playhead)
        split.setEnabled(zoom['start']+1/self.fps<=self.position<=zoom['end']-1/self.fps)
        menu.addAction('Duplicate',self.duplicate_zoom);menu.addSeparator();menu.addAction('Remove',self.delete_selected)
