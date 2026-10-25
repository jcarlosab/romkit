"""Reinsert edited export PNGs into a new ISO, with fixed resource extents."""
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import struct
import tempfile
import zlib

from romkit_core.adapters.registry import enabled_adapters
from romkit_core.analysis.containers import _children, recognized_container, Traversal
from romkit_core.analysis.gim import decode_gim
from romkit_core.errors import ValidationError
from romkit_core.image.pixels import png_rgba
from romkit_core.platforms.iso9660 import Iso9660Reader
from romkit_core.project.rebuild import _digest
from romkit_core.tasks import report


@dataclass(frozen=True)
class ImageBuildResult:
    path: Path
    images: int
    resources: int


def _safe_file(root, relative):
    relative = Path(relative)
    if relative.is_absolute() or any(p in ('..', '') for p in relative.parts):
        raise ValidationError('Ruta de imagen fuera del proyecto')
    path = root / relative
    if not path.resolve().is_relative_to(root) or any(p.is_symlink() for p in (path,*path.parents)):
        raise ValidationError('No se admiten enlaces ni rutas fuera del proyecto de imágenes')
    if not path.is_file() or path.stat().st_size > 64*1024*1024:
        raise ValidationError('Falta una imagen exportada o supera el límite de 64 MiB')
    return path


def _compress(data, capacity, gzip=False):
    choices=[]
    for strategy in (zlib.Z_DEFAULT_STRATEGY,zlib.Z_FILTERED,zlib.Z_RLE,zlib.Z_HUFFMAN_ONLY,zlib.Z_FIXED):
        encoder=zlib.compressobj(9,zlib.DEFLATED,31 if gzip else 15,9,strategy)
        choices.append(encoder.compress(data)+encoder.flush())
    stored=min(choices,key=len)
    if len(stored)>capacity:
        raise ValidationError(f'Recurso comprimido: necesita {len(stored)} bytes y dispone de {capacity}; ampliación no implementada')
    return stored


def rewrite_payload(data, logical, leaf, edit, depth=0):
    if depth>8:
        raise ValidationError('Demasiados contenedores anidados')
    if logical==leaf:
        if recognized_container(data):
            raise ValidationError('Contenedor sin índice compatible: no puede reinsertarse mediante escaneo')
        return edit(data)
    children=list(_children(data,logical,Traversal()))
    chosen=[(i,name,raw) for i,(name,raw) in enumerate(children) if leaf==name or leaf.startswith(name+'!')]
    if len(chosen)!=1:
        raise ValidationError('La procedencia de la imagen no coincide con un contenedor compatible')
    i,name,raw=chosen[0]
    replacement=rewrite_payload(raw,name,leaf,edit,depth+1)
    if len(replacement)!=len(raw):
        raise ValidationError('No se admite crecimiento de imágenes dentro del contenedor')
    if data.startswith(b'BND\0'):
        _,at,length,_=struct.unpack_from('<4I',data,32+i*16)
        ranges=[struct.unpack_from('<2I',data,32+n*16+4) for n in range(len(children))]
        if any(n!=i and at<other+size and other<at+length for n,(other,size) in enumerate(ranges)):
            raise ValidationError('Entradas BND solapadas')
        output=bytearray(data);output[at:at+length]=replacement
        return bytes(output)
    if name==logical+'!decompressed':
        stored=_compress(replacement,len(data),data.startswith(b'\x1f\x8b'))
        return stored.ljust(len(data),b'\0')
    raise ValidationError('Escritura del contenedor no implementada (ZIP u otra variante)')


def _edit_resource(raw, root_name, edits, origin):
    output=raw
    for entry,png in edits:
        kind=entry['source_format']
        if kind=='gmio':
            if origin['adapter']!='digimon':
                raise ValidationError('GMIO requiere el adaptador Digimon')
            from romkit_core.adapters.digimon.images import decode_gmio, replace_gmio
            at=entry['offset'];original=decode_gmio(raw,at,origin['base'],origin['structure'])
            if original is None or hashlib.sha256(original.png).hexdigest()!=entry['sha256']:
                raise ValidationError('Hash de imagen GMIO original incorrecto')
            output=replace_gmio(output,at,origin['base'],origin['structure'],png)
            continue
        def edit(payload):
            at,length=entry['offset'],entry['length_bytes']
            if not isinstance(at,int) or not isinstance(length,int) or at<0 or length<=0 or at+length>len(payload):
                raise ValidationError('Límites de imagen incorrectos')
            old=payload[at:at+length]
            if kind=='gim':
                from romkit_core.adapters.pokapoka.images import replace_gim
                pictures=decode_gim(old)
                index=entry['surface']
                if not 0<=index<len(pictures) or hashlib.sha256(pictures[index].png).hexdigest()!=entry['sha256']:
                    raise ValidationError('Hash de imagen GIM original incorrecto')
                new=replace_gim(old,index,png)
            elif kind=='png':
                if hashlib.sha256(old).hexdigest()!=entry['sha256']:
                    raise ValidationError('Hash del PNG original incorrecto')
                w,h,_=png_rgba(old)
                if png_rgba(png)[:2]!=(w,h) or len(png)>length:
                    raise ValidationError(f'PNG: conserva {w}x{h}; necesita {len(png)} bytes y dispone de {length}')
                new=png.ljust(length,b'\0')
            else:
                raise ValidationError(f'Escritura de imágenes {kind} no implementada')
            result=bytearray(payload);result[at:at+length]=new
            return bytes(result)
        output=rewrite_payload(output,root_name,entry['source'],edit)
    # Shared GMIO data may have several views: changes to an unselected view are rejected.
    if origin['adapter']=='digimon' and origin['base'] is not None:
        from romkit_core.adapters.digimon.images import decode_gmio
        targets={e['offset']:png_rgba(png)[2] for e,png in edits if e['source_format']=='gmio'}
        cursor=0
        while (cursor:=raw.find(b'GMIO',cursor,origin['structure']))>=0:
            try:
                before=decode_gmio(raw,cursor,origin['base'],origin['structure'])
            except ValueError:
                cursor+=4;continue
            if before:
                after=decode_gmio(output,cursor,origin['base'],origin['structure'])
                expected=targets.get(cursor,png_rgba(before.png)[2])
                if after is None or png_rgba(after.png)[2]!=expected:
                    raise ValidationError('Datos GMIO compartidos: el cambio afecta a otra imagen; no se publicará la ISO')
            cursor+=4
    return output


def rebuild_images(project, workspace, image, destination, *, progress=None):
    project=Path(project).resolve(strict=True);destination=Path(destination).absolute()
    if destination.exists() or destination.is_symlink() or destination.resolve()==image.path.resolve():
        raise ValidationError('Elige un nombre nuevo para la ISO con imágenes')
    manifest_path=_safe_file(project,'imagenes.json')
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('schema_version')!=2:
        raise ValidationError('Exportación antigua: vuelve a buscar y extraer imágenes para crear metadata de reinserción')
    if (image.selected_platform!='psp' or manifest.get('source_sha256')!=image.sha256
            or workspace.load_source_metadata().sha256!=image.sha256 or _digest(image.path,progress)!=image.sha256):
        raise ValidationError('Las imágenes no corresponden a la ROM PSP original abierta')
    entries=manifest.get('images',[])
    if not isinstance(entries,list) or len(entries)>100000:
        raise ValidationError('Manifiesto de imágenes demasiado grande o inválido')
    groups=defaultdict(list);cache={};origins={};count=0;modified_bytes=0;claims={};targets={}
    enabled={a.id for a in enabled_adapters()}
    for entry in entries:
        path=_safe_file(project,entry['file'])
        if path not in cache:
            content=path.read_bytes();digest=hashlib.sha256(content).hexdigest()
            cache[path]=(digest,content if digest!=entry['sha256'] else None)
            if digest!=entry['sha256']:
                modified_bytes+=len(content)
                if modified_bytes>256*1024*1024:
                    raise ValidationError('Límite de 256 MiB de imágenes modificadas por importación; divide el trabajo en lotes')
        digest,png=cache[path]
        if digest==entry['sha256']:
            continue
        if png is None:raise ValidationError('Hash original contradictorio para un PNG deduplicado')
        png_rgba(png)
        origin=entry.get('origin')
        if not origin or origin.get('adapter') not in enabled|{'file'}:
            raise ValidationError('El adaptador de imágenes no está habilitado en esta versión')
        if entry['source_format']=='gim' and 'pokapoka' not in enabled:
            raise ValidationError('La escritura GIM requiere el perfil Poka Poka')
        key=json.dumps(origin,sort_keys=True)
        claim=(origin['adapter'],origin.get('archive',origin.get('logical_path')),origin.get('slot'),json.dumps(origin.get('location'),sort_keys=True))
        if claim in claims and claims[claim]!=key:
            raise ValidationError('Procedencias contradictorias para el mismo recurso')
        claims[claim]=key
        target=(key,entry['source'],entry['offset'],entry['surface'])
        if target in targets:
            if targets[target]!=digest:raise ValidationError('Dos PNG distintos intentan sustituir la misma imagen')
            continue
        targets[target]=digest
        origins[key]=origin;groups[key].append((entry,png));count+=1
    reader=Iso9660Reader()
    with tempfile.TemporaryDirectory(prefix='romkit-images-build-') as temporary:
        staging=Path(temporary);replacements={};prepared={}
        with reader.open(image.path) as iso:
            iso_entries={e.logical_path:e for e in reader.walk(iso) if not e.is_directory}
            def extract(logical):
                if logical not in iso_entries:
                    raise ValidationError('Falta el recurso original en la ISO')
                path=reader.destination_path(staging,iso_entries[logical])
                if not path.exists():reader.extract_file(iso,iso_entries[logical],staging)
                return path
            for n,(key,edits) in enumerate(groups.items()):
                origin=origins[key];adapter=origin['adapter']
                report(progress,n,len(groups),'Reconstruyendo imágenes')
                if adapter=='pokapoka':
                    from romkit_core.adapters.pokapoka.reader import iter_archive_members
                    archive=origin['archive'];parent=archive.rsplit('/',1)[0];stem=Path(archive).stem
                    if archive not in prepared:
                        for suffix in ('FAT','BHD','BND'):extract(f'{parent}/{stem}.{suffix}')
                        # Only image members are cached; all paths and offsets come from the fresh ISO.
                        prepared[archive]={o['slot']:(raw,o) for _,_,raw,o in iter_archive_members(staging/parent,parent,stem=stem,on_error=lambda *a:None) if o['slot'] in {origins[k].get('slot') for k in groups if origins[k].get('archive')==archive}}
                    raw,fresh=prepared[archive].get(origin['slot'],(None,None))
                    if fresh is None or {'adapter':'pokapoka',**fresh}!=origin:
                        raise ValidationError('El origen BHD de la imagen no coincide con la ROM')
                    root_name=origin['logical_path'];output=_edit_resource(raw,root_name,edits,origin)
                    bundle=staging/archive
                    bhd=staging/f'{parent}/{stem}.BHD'
                    index_data=bhd.read_bytes()
                    for slot,at in enumerate(range(28,len(index_data),40)):
                        _,sector,raw_size,stored_size=struct.unpack_from('<4I',index_data,at)
                        other=sector*1024;size=stored_size or raw_size
                        if slot!=origin['slot'] and other<origin['offset']+origin['stored_size'] and origin['offset']<other+size:
                            raise ValidationError('Miembros BHD con datos compartidos o solapados; escritura no implementada')
                    offsets=sorted({struct.unpack_from('<I',index_data,at+4)[0]*1024 for at in range(28,len(index_data),40)})
                    limit=next((at for at in offsets if at>origin['offset']),bundle.stat().st_size)
                    if limit<origin['offset']+origin['stored_size']:
                        raise ValidationError('Miembros BHD solapados')
                    capacity=limit-origin['offset']
                    with bundle.open('rb') as stream:
                        stream.seek(origin['offset']+origin['stored_size'])
                        # Do not consume occupied padding, even within the sector allocation.
                        remaining=capacity-origin['stored_size']
                        while remaining:
                            block=stream.read(min(remaining,1024*1024));remaining-=len(block)
                            if not block or any(block):
                                capacity=origin['stored_size'];break
                    stored=_compress(output,capacity) if origin['compression']=='zlib' else output
                    with bundle.open('r+b') as stream:stream.seek(origin['offset']);stream.write(stored.ljust(origin['stored_size'],b'\0'))
                    if origin['compression']=='zlib':
                        data=bytearray(bhd.read_bytes())
                        struct.pack_into('<I',data,28+origin['slot']*40+12,len(stored));bhd.write_bytes(data)
                        replacements[f'{parent}/{stem}.BHD']=bhd
                    replacements[archive]=bundle
                elif adapter=='digimon':
                    from romkit_core.adapters.digimon.archive import iter_arcv
                    archive=origin['archive'];parent=archive.rsplit('/',1)[0]
                    if archive not in prepared:
                        index=extract(archive)
                        for logical in iso_entries:
                            if logical.rsplit('/',1)[0]==parent and re.fullmatch(r'ARCV\d+\.BIN',logical.rsplit('/',1)[-1]):extract(logical)
                        wanted={origins[k]['location']['index_record'] for k in groups if origins[k].get('archive')==archive}
                        selected={};locations=[]
                        for name,raw,base,structure,loc in iter_arcv(index,with_locations=True):
                            locations.append(loc)
                            if loc['index_record'] in wanted:selected[loc['index_record']]=(name,raw,base,structure,loc)
                        for _,_,_,_,loc in selected.values():
                            if any(o['index_record']!=loc['index_record'] and o['volume']==loc['volume'] and o['offset']<loc['offset']+loc['size'] and loc['offset']<o['offset']+o['size'] for o in locations):
                                raise ValidationError('Miembros ARCV con datos compartidos o solapados; escritura no implementada')
                        prepared[archive]=selected
                    name,raw,base,structure,loc=prepared[archive][origin['location']['index_record']]
                    fresh={'adapter':'digimon','archive':archive,'member':name,'location':loc,'base':base,'structure':structure,'sha256':hashlib.sha256(raw).hexdigest()}
                    if fresh!=origin:raise ValidationError('El origen ARCV de la imagen no coincide con la ROM')
                    output=_edit_resource(raw,archive+'!arcv/'+name,edits,origin)
                    logical=f'{parent}/ARCV{loc["volume"]}.BIN';path=staging/logical
                    with path.open('r+b') as stream:stream.seek(loc['offset']);stream.write(output)
                    replacements[logical]=path
                else:
                    logical=origin['logical_path'];path=extract(logical);raw=path.read_bytes()
                    if hashlib.sha256(raw).hexdigest()!=origin['sha256']:raise ValidationError('Hash del recurso original incorrecto')
                    output=_edit_resource(raw,logical,edits,origin);path.write_bytes(output);replacements[logical]=path
                if len(output)!=len(raw):raise ValidationError('El tamaño del recurso ha cambiado')
                # Verify the stored bytes through decompression before publication.
                if adapter=='pokapoka':
                    with bundle.open('rb') as stream:stream.seek(origin['offset']);check=stream.read(len(stored))
                    if (zlib.decompress(check) if origin['compression']=='zlib' else check)!=output:
                        raise ValidationError('La verificación del contenedor reconstruido ha fallado')
        reader.patch_copy(image.path,destination,replacements,progress=progress,expected_sha256=image.sha256)
    return ImageBuildResult(destination,count,len(groups))
