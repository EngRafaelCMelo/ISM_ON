from auth import MIN_PASSWORD_LENGTH, UserStore, hash_password, verify_password


def test_password_hash_uses_salt_and_authentication_profiles(tmp_path):
    first = hash_password("senha-segura-1")
    second = hash_password("senha-segura-1")
    assert first != second
    assert verify_password("senha-segura-1", first)
    assert not verify_password("errada", first)

    store = UserStore(str(tmp_path / "users.json"))
    assert not store.has_users()
    store.create_user("operador", "senha-segura-1", "operator")
    assert store.authenticate("operador", "senha-segura-1")["role"] == "operator"
    assert store.get_role("operador") == "operator"
    try:
        store.create_user("bad", "x", "admin")
    except ValueError as error:
        assert str(MIN_PASSWORD_LENGTH) in str(error)
    else:
        raise AssertionError("senha curta deveria ser rejeitada")
