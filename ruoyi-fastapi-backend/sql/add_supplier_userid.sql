-- 加工方表新增 user_id 字段，关联系统登录账号
ALTER TABLE entrust_suppliers ADD COLUMN IF NOT EXISTS user_id BIGINT;
COMMENT ON COLUMN entrust_suppliers.user_id IS '关联系统用户ID（加工方登录账号）';

-- 创建测试加工方用户（密码 admin123 的 BCrypt hash）
INSERT INTO sys_user (user_id, dept_id, user_name, nick_name, user_type, email, phonenumber, sex, password, status, del_flag, create_by, create_time)
VALUES (10, NULL, 'qd_hexing', '青岛和兴嘉业', '00', '', '13210828919', '0',
        '$2a$10$7JB720yubVSZvUI0rEqK/.VqGOZTH.ulu33dHOiBE8ByOhJIrdAu2', '0', '0', 'admin', now());

-- 绑定：青岛和兴嘉业 (supplier_id=1) → 用户 qd_hexing (user_id=10)
UPDATE entrust_suppliers SET user_id = 10 WHERE id = 1;

-- 给测试用户分配"加工方"角色 (role_id=103)
INSERT INTO sys_user_role (user_id, role_id) VALUES (10, 103);

SELECT setval('sys_user_user_id_seq', 100, false);
