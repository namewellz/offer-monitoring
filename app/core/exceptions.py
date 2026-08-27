class SourceUnavailableError(Exception):
    pass


class SourceBlockedError(Exception):
    pass


class FlyerNotFoundError(Exception):
    pass


class ParserChangedError(Exception):
    pass


class AssetDownloadError(Exception):
    pass


class ExtractionError(Exception):
    pass
