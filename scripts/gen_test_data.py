#!/usr/bin/env python3
import os

BASE = "/tmp/nas_media_test/source"


def fake_file(path, size_mb=0.001):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    size = int(size_mb * 1024 * 1024)
    with open(path, "wb") as f:
        if size > 0:
            chunk = b"\x00" * 65536
            written = 0
            while written < size:
                n = min(65536, size - written)
                f.write(chunk[:n])
                written += n


def build_all():
    os.makedirs(BASE, exist_ok=True)

    # A01
    d = f"{BASE}/A01_标准电影_单视频单字幕"
    fake_file(f"{d}/The.Matrix.1999.1080p.BluRay.x264.mkv", 15)
    fake_file(f"{d}/The.Matrix.1999.1080p.BluRay.x264.srt", 0.08)
    fake_file(f"{d}/The.Matrix.1999.1080p.BluRay.x264.nfo", 0.005)

    # A02
    d = f"{BASE}/A02_标准电影_多字幕"
    fake_file(f"{d}/Inception.2010.2160p.UHD.BluRay.x265.mkv", 25)
    fake_file(f"{d}/Inception.2010.2160p.chi.srt", 0.065)
    fake_file(f"{d}/Inception.2010.2160p.eng.srt", 0.058)
    fake_file(f"{d}/Inception.2010.2160p.jpn.ass", 0.042)
    fake_file(f"{d}/Inception.2010.nfo", 0.003)

    # A03
    d = f"{BASE}/A03_电影_带海报和元数据"
    fake_file(f"{d}/Interstellar.2014.1080p.BluRay.mkv", 18)
    fake_file(f"{d}/Interstellar.2014.1080p.chi&eng.srt", 0.072)
    fake_file(f"{d}/Interstellar.2014.nfo", 0.004)
    fake_file(f"{d}/Interstellar.2014-poster.jpg", 0.35)
    fake_file(f"{d}/Interstellar.2014-fanart.jpg", 0.8)
    fake_file(f"{d}/Interstellar.2014-banner.jpg", 0.12)

    # A04
    d = f"{BASE}/A04_电影_带BT广告文件"
    fake_file(f"{d}/Parasite.2019.1080p.BluRay.x264.mkv", 12)
    fake_file(f"{d}/Parasite.2019.1080p.chi.srt", 0.055)
    fake_file(f"{d}/www.YTS.mx.url", 0.001)
    fake_file(f"{d}/YTS.mx.txt", 0.002)
    fake_file(f"{d}/Parasite.2019.nfo", 0.003)
    fake_file(f"{d}/Torrent-downloaded-from-demo.txt", 0.001)

    # A05
    d = f"{BASE}/A05_电影_带广告图片"
    fake_file(f"{d}/1917.2019.1080p.BluRay.x264.mkv", 14)
    fake_file(f"{d}/1917.2019.chi.srt", 0.048)
    fake_file(f"{d}/RARBG.mp4", 8)
    fake_file(f"{d}/RARBG.txt", 0.001)
    fake_file(f"{d}/RARBG.jpg", 0.15)
    fake_file(f"{d}/RARBG.do-not-mirror-this-folder.txt", 0.001)

    # A06
    d = f"{BASE}/A06_电影_带Sample目录"
    fake_file(f"{d}/Dunkirk.2017.1080p.BluRay.x264/Dunkirk.2017.1080p.BluRay.x264.mkv", 16)
    fake_file(f"{d}/Dunkirk.2017.1080p.BluRay.x264/Dunkirk.2017.chi.srt", 0.05)
    fake_file(f"{d}/Dunkirk.2017.1080p.BluRay.x264/Sample/Dunkirk.2017.1080p.Sample.mkv", 50)
    fake_file(f"{d}/Dunkirk.2017.1080p.BluRay.x264/Sample/Sample.nfo", 0.001)

    # A07
    d = f"{BASE}/A07_电影_多版本同目录"
    fake_file(f"{d}/Blade.Runner.2049.2017.1080p.mkv", 10)
    fake_file(f"{d}/Blade.Runner.2049.2017.720p.mkv", 5)
    fake_file(f"{d}/Blade.Runner.2049.2017.chi.srt", 0.045)
    fake_file(f"{d}/Blade.Runner.2049.2017.nfo", 0.003)

    # A08
    d = f"{BASE}/A08_电影_蓝光原盘结构"
    fake_file(f"{d}/The.Godfather.1972.UHD.BluRay/BDMV/index.bdmv", 0.001)
    fake_file(f"{d}/The.Godfather.1972.UHD.BluRay/BDMV/MovieObject.bdmv", 0.002)
    fake_file(f"{d}/The.Godfather.1972.UHD.BluRay/BDMV/STREAM/00001.m2ts", 80)
    fake_file(f"{d}/The.Godfather.1972.UHD.BluRay/BDMV/STREAM/00002.m2ts", 0.2)
    fake_file(f"{d}/The.Godfather.1972.UHD.BluRay/BDMV/CLIPINF/00001.clpi", 0.005)
    fake_file(f"{d}/The.Godfather.1972.UHD.BluRay/BDMV/CLIPINF/00002.clpi", 0.003)
    fake_file(f"{d}/The.Godfather.1972.UHD.BluRay/BDMV/PLAYLIST/00001.mpls", 0.001)
    fake_file(f"{d}/The.Godfather.1972.UHD.BluRay/CERTIFICATE/id.bdmv", 0.001)
    fake_file(f"{d}/The.Godfather.1972.UHD.BluRay/The.Godfather.1972.nfo", 0.004)

    # A09
    d = f"{BASE}/A09_电影_极小视频混淆"
    fake_file(f"{d}/Avatar.2009.1080p.mkv", 20)
    fake_file(f"{d}/Avatar.2009.chi.srt", 0.06)
    fake_file(f"{d}/Avatar.2009.Trailer.1080p.mkv", 180)
    fake_file(f"{d}/Avatar.2009.Behind.the.Scenes.mkv", 300)
    fake_file(f"{d}/Avatar.2009.nfo", 0.003)

    # A10
    d = f"{BASE}/A10_电影_纯视频无其他"
    fake_file(f"{d}/The.Shawshank.Redemption.1994.1080p.mkv", 12)

    # B01
    d = f"{BASE}/B01_剧集_标准S01结构"
    fake_file(f"{d}/Breaking.Bad.S01/Breaking.Bad.S01E01.1080p.mkv", 4)
    fake_file(f"{d}/Breaking.Bad.S01/Breaking.Bad.S01E02.1080p.mkv", 3.8)
    fake_file(f"{d}/Breaking.Bad.S01/Breaking.Bad.S01E03.1080p.mkv", 4.2)
    fake_file(f"{d}/Breaking.Bad.S01/Breaking.Bad.S01E01.chi.srt", 0.04)
    fake_file(f"{d}/Breaking.Bad.S01/Breaking.Bad.S01E02.chi.srt", 0.038)
    fake_file(f"{d}/Breaking.Bad.S01/Breaking.Bad.S01E03.chi.srt", 0.042)

    # B02
    d = f"{BASE}/B02_剧集_带季封面"
    fake_file(f"{d}/Game.of.Thrones.S02/Game.of.Thrones.S02E01.1080p.mkv", 3.5)
    fake_file(f"{d}/Game.of.Thrones.S02/Game.of.Thrones.S02E02.1080p.mkv", 3.2)
    fake_file(f"{d}/Game.of.Thrones.S02/Game.of.Thrones.S02.nfo", 0.005)
    fake_file(f"{d}/Game.of.Thrones.S02/Season02-poster.jpg", 0.2)
    fake_file(f"{d}/Game.of.Thrones.S02/fanart.jpg", 0.5)

    # B03
    d = f"{BASE}/B03_剧集_带广告和说明"
    fake_file(f"{d}/The.Witcher.S01/The.Witcher.S01E01.2160p.mkv", 8)
    fake_file(f"{d}/The.Witcher.S01/The.Witcher.S01E02.2160p.mkv", 7.5)
    fake_file(f"{d}/The.Witcher.S01/The.Witcher.S01E01.chi.srt", 0.045)
    fake_file(f"{d}/The.Witcher.S01/The.Witcher.S01E02.chi.srt", 0.042)
    fake_file(f"{d}/The.Witcher.S01/Downloaded.from.1337x.txt", 0.002)
    fake_file(f"{d}/The.Witcher.S01/www.1337x.to.url", 0.001)
    fake_file(f"{d}/The.Witcher.S01/The.Witcher.S01.nfo", 0.003)

    # B04
    d = f"{BASE}/B04_剧集_多季混合"
    fake_file(f"{d}/Stranger.Things/Season 1/Stranger.Things.S01E01.1080p.mkv", 3)
    fake_file(f"{d}/Stranger.Things/Season 1/Stranger.Things.S01E01.chi.srt", 0.035)
    fake_file(f"{d}/Stranger.Things/Season 2/Stranger.Things.S02E01.1080p.mkv", 3.5)
    fake_file(f"{d}/Stranger.Things/Season 2/Stranger.Things.S02E01.chi.srt", 0.038)
    fake_file(f"{d}/Stranger.Things/tvshow.nfo", 0.004)

    # B05
    d = f"{BASE}/B05_剧集_带预告目录"
    fake_file(f"{d}/The.Mandalorian.S01/The.Mandalorian.S01E01.2160p.mkv", 6)
    fake_file(f"{d}/The.Mandalorian.S01/The.Mandalorian.S01E02.2160p.mkv", 5.8)
    fake_file(f"{d}/The.Mandalorian.S01/Trailers/S01.Trailer.1080p.mkv", 120)
    fake_file(f"{d}/The.Mandalorian.S01/Trailers/S01.Teaser.720p.mkv", 60)
    fake_file(f"{d}/The.Mandalorian.S01/The.Mandalorian.S01.nfo", 0.003)

    # B06
    d = f"{BASE}/B06_剧集_带花絮目录"
    fake_file(f"{d}/Chernobyl.S01/Chernobyl.S01E01.1080p.mkv", 4)
    fake_file(f"{d}/Chernobyl.S01/Chernobyl.S01E02.1080p.mkv", 3.8)
    fake_file(f"{d}/Chernobyl.S01/Extras/Behind.the.Scenes.1080p.mkv", 500)
    fake_file(f"{d}/Chernobyl.S01/Extras/Interview.1080p.mkv", 300)
    fake_file(f"{d}/Chernobyl.S01/Chernobyl.S01.nfo", 0.003)

    # B07
    d = f"{BASE}/B07_剧集_整季单文件"
    fake_file(f"{d}/The.Office.S03/The.Office.S03E01-E10.1080p.mkv", 15)
    fake_file(f"{d}/The.Office.S03/The.Office.S03.chi.srt", 0.12)
    fake_file(f"{d}/The.Office.S03/The.Office.S03.nfo", 0.004)

    # B08
    d = f"{BASE}/B08_剧集_带字幕子目录"
    fake_file(f"{d}/Money.Heist.S01/Money.Heist.S01E01.1080p.mkv", 3.5)
    fake_file(f"{d}/Money.Heist.S01/Money.Heist.S01E02.1080p.mkv", 3.2)
    fake_file(f"{d}/Money.Heist.S01/Subs/Money.Heist.S01E01.chi.srt", 0.038)
    fake_file(f"{d}/Money.Heist.S01/Subs/Money.Heist.S01E01.eng.srt", 0.035)
    fake_file(f"{d}/Money.Heist.S01/Subs/Money.Heist.S01E02.chi.srt", 0.036)
    fake_file(f"{d}/Money.Heist.S01/Subs/Money.Heist.S01E02.eng.srt", 0.033)
    fake_file(f"{d}/Money.Heist.S01/Money.Heist.S01.nfo", 0.003)

    # C01
    d = f"{BASE}/C01_动漫_标准结构"
    fake_file(f"{d}/[SubGroup] Sword Art Online - 01 [1080p].mkv", 1.2)
    fake_file(f"{d}/[SubGroup] Sword Art Online - 02 [1080p].mkv", 1.1)
    fake_file(f"{d}/[SubGroup] Sword Art Online - 01.chi.ass", 0.025)
    fake_file(f"{d}/[SubGroup] Sword Art Online - 02.chi.ass", 0.023)

    # C02
    d = f"{BASE}/C02_动漫_带字体文件"
    fake_file(f"{d}/[ANIME-GROUP] Demon Slayer - 01 [1080p].mkv", 1.5)
    fake_file(f"{d}/[ANIME-GROUP] Demon Slayer - 02 [1080p].mkv", 1.4)
    fake_file(f"{d}/[ANIME-GROUP] Demon Slayer - 01.chi.ass", 0.03)
    fake_file(f"{d}/Fonts/font1.ttf", 5)
    fake_file(f"{d}/Fonts/font2.otf", 3)
    fake_file(f"{d}/Fonts/font3.ttf", 4)
    fake_file(f"{d}/[ANIME-GROUP] Demon Slayer.nfo", 0.002)

    # C03
    d = f"{BASE}/C03_动漫_带CD镜像"
    fake_file(f"{d}/[R2J] Evangelion - 01 [BD 1080p].mkv", 2)
    fake_file(f"{d}/[R2J] Evangelion - 02 [BD 1080p].mkv", 1.8)
    fake_file(f"{d}/[R2J] Evangelion - 01.chi.ass", 0.028)
    fake_file(f"{d}/CD/OST01.flac", 40)
    fake_file(f"{d}/CD/OST02.flac", 35)
    fake_file(f"{d}/CD/cover.jpg", 0.2)
    fake_file(f"{d}/[R2J] Evangelion.nfo", 0.002)

    # C04
    d = f"{BASE}/C04_动漫_带SP和OVA"
    fake_file(f"{d}/[GROUP] Attack on Titan - 01 [1080p].mkv", 1.3)
    fake_file(f"{d}/[GROUP] Attack on Titan - 02 [1080p].mkv", 1.2)
    fake_file(f"{d}/[GROUP] Attack on Titan - SP01 [1080p].mkv", 200)
    fake_file(f"{d}/[GROUP] Attack on Titan - OAD01 [1080p].mkv", 500)
    fake_file(f"{d}/[GROUP] Attack on Titan - 01.chi.ass", 0.022)
    fake_file(f"{d}/[GROUP] Attack on Titan.nfo", 0.002)

    # C05
    d = f"{BASE}/C05_动漫_带广告图片"
    fake_file(f"{d}/[SubGroup] One Piece - 1000 [1080p].mkv", 800)
    fake_file(f"{d}/[SubGroup] One Piece - 1001 [1080p].mkv", 780)
    fake_file(f"{d}/[SubGroup] One Piece - 1000.chi.ass", 0.02)
    fake_file(f"{d}/[SubGroup] ad_banner.jpg", 0.1)
    fake_file(f"{d}/[SubGroup] recruitment.txt", 0.002)
    fake_file(f"{d}/[SubGroup] One Piece.nfo", 0.001)

    # C06
    d = f"{BASE}/C06_动漫_内封字幕无外挂"
    fake_file(f"{d}/[GROUP] Jujutsu Kaisen - 01 [1080p].mkv", 1.1)
    fake_file(f"{d}/[GROUP] Jujutsu Kaisen - 02 [1080p].mkv", 1.0)

    # D01
    d = f"{BASE}/D01_纪录片_标准"
    fake_file(f"{d}/Planet.Earth.III.S01E01.2160p.mkv", 8)
    fake_file(f"{d}/Planet.Earth.III.S01E02.2160p.mkv", 7.5)
    fake_file(f"{d}/Planet.Earth.III.S01E01.chi.srt", 0.05)
    fake_file(f"{d}/Planet.Earth.III.nfo", 0.003)

    # D02
    d = f"{BASE}/D02_纪录片_带花絮"
    fake_file(f"{d}/Blue.Planet.II.S01E01.1080p.mkv", 5)
    fake_file(f"{d}/Blue.Planet.II.S01E02.1080p.mkv", 4.8)
    fake_file(f"{d}/Extras/Behind.the.Lens.1080p.mkv", 400)
    fake_file(f"{d}/Extras/Interview.1080p.mkv", 250)
    fake_file(f"{d}/Blue.Planet.II.nfo", 0.003)

    # D03
    d = f"{BASE}/D03_特别篇_单文件"
    fake_file(f"{d}/The.World.At.War.1973.1080p.Remastered.mkv", 8)
    fake_file(f"{d}/The.World.At.War.1973.nfo", 0.004)

    # D04
    d = f"{BASE}/D04_纪录片_带PDF手册"
    fake_file(f"{d}/Cosmos.A.Spacetime.Odyssey.S01E01.1080p.mkv", 4)
    fake_file(f"{d}/Cosmos.A.Spacetime.Odyssey.S01E02.1080p.mkv", 3.8)
    fake_file(f"{d}/Cosmos.A.Spacetime.Odyssey.S01E01.chi.srt", 0.042)
    fake_file(f"{d}/Study.Guide.pdf", 15)
    fake_file(f"{d}/Cosmos.nfo", 0.002)

    # D05
    d = f"{BASE}/D05_纪录片_带ISO"
    fake_file(f"{d}/National.Geographic.Collection/NatGeo.Ep01.1080p.mkv", 3)
    fake_file(f"{d}/National.Geographic.Collection/NatGeo.Ep02.1080p.mkv", 2.8)
    fake_file(f"{d}/National.Geographic.Collection/Bonus_Disc.iso", 4.7)

    # E01
    d = f"{BASE}/E01_PT站_带NFO和截图"
    fake_file(f"{d}/2001.A.Space.Odyssey.1968.2160p.UHD.BluRay.REMUX.mkv", 55)
    fake_file(f"{d}/2001.A.Space.Odyssey.1968.chi.srt", 0.055)
    fake_file(f"{d}/2001.A.Space.Odyssey.1968.nfo", 0.008)
    fake_file(f"{d}/2001.A.Space.Odyssey.1968-thumb1.jpg", 0.3)
    fake_file(f"{d}/2001.A.Space.Odyssey.1968-thumb2.jpg", 0.28)
    fake_file(f"{d}/2001.A.Space.Odyssey.1968-thumb3.jpg", 0.31)
    fake_file(f"{d}/2001.A.Space.Odyssey.1968-thumb4.jpg", 0.29)

    # E02
    d = f"{BASE}/E02_PT站_带MediaInfo"
    fake_file(f"{d}/Lawrence.of.Arabia.1962.1080p.BluRay.REMUX.mkv", 40)
    fake_file(f"{d}/Lawrence.of.Arabia.1962.chi.srt", 0.048)
    fake_file(f"{d}/Lawrence.of.Arabia.1962.nfo", 0.006)
    fake_file(f"{d}/MediaInfo.txt", 0.003)
    fake_file(f"{d}/Lawrence.of.Arabia.1962-poster.jpg", 0.25)

    # E03
    d = f"{BASE}/E03_PT站_多CD结构"
    fake_file(f"{d}/Schindlers.List.1993.1080p.BluRay/CD1/Schindlers.List.1993.CD1.1080p.mkv", 8)
    fake_file(f"{d}/Schindlers.List.1993.1080p.BluRay/CD2/Schindlers.List.1993.CD2.1080p.mkv", 7)
    fake_file(f"{d}/Schindlers.List.1993.1080p.BluRay/Schindlers.List.1993.chi.srt", 0.055)
    fake_file(f"{d}/Schindlers.List.1993.1080p.BluRay/Schindlers.List.1993.nfo", 0.005)

    # E04
    d = f"{BASE}/E04_PT站_带校验文件"
    fake_file(f"{d}/The.Seven.Samurai.1954.1080p.BluRay.mkv", 15)
    fake_file(f"{d}/The.Seven.Samurai.1954.chi.srt", 0.04)
    fake_file(f"{d}/The.Seven.Samurai.1954.nfo", 0.004)
    fake_file(f"{d}/The.Seven.Samurai.1954.sfv", 0.002)
    fake_file(f"{d}/The.Seven.Samurai.1954.nfo.bak", 0.004)

    # E05
    d = f"{BASE}/E05_PT站_REMUX带完整结构"
    fake_file(f"{d}/Casablanca.1942.1080p.BluRay.REMUX/Casablanca.1942.1080p.REMUX.mkv", 30)
    fake_file(f"{d}/Casablanca.1942.1080p.BluRay.REMUX/Casablanca.1942.chi.srt", 0.035)
    fake_file(f"{d}/Casablanca.1942.1080p.BluRay.REMUX/Casablanca.1942.nfo", 0.005)
    fake_file(f"{d}/Casablanca.1942.1080p.BluRay.REMUX/Casablanca.1942-poster.jpg", 0.2)
    fake_file(f"{d}/Casablanca.1942.1080p.BluRay.REMUX/Proof/proof.jpg", 0.15)

    # E06
    d = f"{BASE}/E06_PT站_带说明文件"
    fake_file(f"{d}/Citizen.Kane.1941.1080p.BluRay.mkv", 12)
    fake_file(f"{d}/Citizen.Kane.1941.chi.srt", 0.038)
    fake_file(f"{d}/Citizen.Kane.1941.nfo", 0.004)
    fake_file(f"{d}/README.txt", 0.003)
    fake_file(f"{d}/Torrent.Info.txt", 0.002)

    # F01
    d = f"{BASE}/F01_混淆广告_同名小视频"
    fake_file(f"{d}/The.Dark.Knight.2008.1080p.mkv", 15)
    fake_file(f"{d}/The.Dark.Knight.2008.chi.srt", 0.052)
    fake_file(f"{d}/The.Dark.Knight.2008.mkv", 20)
    fake_file(f"{d}/The.Dark.Knight.2008.nfo", 0.003)

    # F02
    d = f"{BASE}/F02_混淆广告_大小写变体"
    fake_file(f"{d}/Inception.2010.1080p.mkv", 12)
    fake_file(f"{d}/Inception.2010.chi.srt", 0.048)
    fake_file(f"{d}/SAMPLE.mp4", 5)
    fake_file(f"{d}/Trailer.720p.mp4", 30)

    # F03
    d = f"{BASE}/F03_中文资源_带说明"
    fake_file(f"{d}/让子弹飞.2010.1080p.BluRay.mkv", 10)
    fake_file(f"{d}/让子弹飞.2010.chi.srt", 0.04)
    fake_file(f"{d}/让子弹飞.2010.nfo", 0.003)
    fake_file(f"{d}/下载说明.txt", 0.002)
    fake_file(f"{d}/免责声明.txt", 0.001)
    fake_file(f"{d}/关注公众号获取更多.txt", 0.001)

    # F04
    d = f"{BASE}/F04_中文资源_带预告"
    fake_file(f"{d}/流浪地球2.2023.2160p.mkv", 25)
    fake_file(f"{d}/流浪地球2.2023.chi.srt", 0.055)
    fake_file(f"{d}/流浪地球2.预告片.1080p.mkv", 150)
    fake_file(f"{d}/流浪地球2.花絮.720p.mkv", 200)
    fake_file(f"{d}/流浪地球2.nfo", 0.003)

    # F05
    d = f"{BASE}/F05_空目录_清理后残留"
    os.makedirs(d, exist_ok=True)

    # F06
    d = f"{BASE}/F06_深层嵌套_空目录"
    os.makedirs(f"{d}/Movie.Collection/Action", exist_ok=True)

    # F07
    d = f"{BASE}/F07_混合文件_全类型"
    fake_file(f"{d}/Everything.Everywhere.2022.1080p.mkv", 10)
    fake_file(f"{d}/Everything.Everywhere.2022.chi.srt", 0.045)
    fake_file(f"{d}/Everything.Everywhere.2022.nfo", 0.003)
    fake_file(f"{d}/poster.jpg", 0.2)
    fake_file(f"{d}/fanart.png", 0.5)
    fake_file(f"{d}/banner.jpg", 0.1)
    fake_file(f"{d}/www.demo-site.com.url", 0.001)
    fake_file(f"{d}/download-info.txt", 0.002)
    fake_file(f"{d}/Sample.mkv", 30)
    fake_file(f"{d}/RARBG.mp4", 8)
    fake_file(f"{d}/.DS_Store", 0.006)
    fake_file(f"{d}/Thumbs.db", 0.02)

    # F08
    d = f"{BASE}/F08_纯音频_非影视"
    fake_file(f"{d}/Album.Collection/track01.flac", 40)
    fake_file(f"{d}/Album.Collection/track02.flac", 35)
    fake_file(f"{d}/Album.Collection/track03.flac", 38)
    fake_file(f"{d}/Album.Collection/cover.jpg", 0.2)
    fake_file(f"{d}/Album.Collection/playlist.m3u", 0.001)

    # F09
    d = f"{BASE}/F09_软件_非影视"
    fake_file(f"{d}/Some.Software.2024/setup.exe", 50)
    fake_file(f"{d}/Some.Software.2024/readme.txt", 0.005)
    fake_file(f"{d}/Some.Software.2024/crack/patch.exe", 10)
    fake_file(f"{d}/Some.Software.2024/docs/manual.pdf", 8)

    # F10
    d = f"{BASE}/F10_图片集_非影视"
    fake_file(f"{d}/Photo.Collection/IMG_001.jpg", 5)
    fake_file(f"{d}/Photo.Collection/IMG_002.jpg", 4)
    fake_file(f"{d}/Photo.Collection/IMG_003.png", 6)
    fake_file(f"{d}/Photo.Collection/metadata.json", 0.002)

    # G01
    d = f"{BASE}/G01_超大文件_4KREMUX"
    fake_file(f"{d}/Ben.Hur.1959.2160p.UHD.BluRay.REMUX.mkv", 80)
    fake_file(f"{d}/Ben.Hur.1959.chi.srt", 0.06)
    fake_file(f"{d}/Ben.Hur.1959.nfo", 0.005)

    # G02
    d = f"{BASE}/G02_极小视频_短视频广告"
    fake_file(f"{d}/Ad.Videos/ad001.mp4", 2)
    fake_file(f"{d}/Ad.Videos/ad002.mp4", 3)
    fake_file(f"{d}/Ad.Videos/ad003.mp4", 1.5)
    fake_file(f"{d}/Ad.Videos/ad004.mp4", 2.5)

    # G03
    d = f"{BASE}/G03_零字节文件"
    fake_file(f"{d}/Empty.Files/movie.mkv", 0)
    fake_file(f"{d}/Empty.Files/subtitle.srt", 0)
    fake_file(f"{d}/Empty.Files/info.nfo", 0)

    # G04
    d = f"{BASE}/G04_特殊字符文件名"
    fake_file(f"{d}/特殊字符测试/电影[2024][4K].mkv", 5)
    fake_file(f"{d}/特殊字符测试/电影[2024].chi.srt", 0.03)
    fake_file(f"{d}/特殊字符测试/电影's cut.nfo", 0.002)
    fake_file(f"{d}/特殊字符测试/电影 & 更多.jpg", 0.1)

    # G05
    d = f"{BASE}/G05_隐藏文件"
    fake_file(f"{d}/Hidden.Files/Movie.2024.1080p.mkv", 8)
    fake_file(f"{d}/Hidden.Files/.hidden_file", 0.001)
    fake_file(f"{d}/Hidden.Files/.gitkeep", 0)
    fake_file(f"{d}/Hidden.Files/Movie.2024.chi.srt", 0.035)

    count = sum(1 for _ in os.walk(BASE))
    print(f"Done: {count} directories created under {BASE}")


if __name__ == "__main__":
    build_all()
